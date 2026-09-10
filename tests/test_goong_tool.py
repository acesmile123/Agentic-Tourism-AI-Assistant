import json

from tourism_agent.tools.goong import GoongPlacesTool


class FakeResponse:
    def __init__(self, payload, invalid_json=False):
        self.payload = payload
        self.invalid_json = invalid_json

    def raise_for_status(self):
        return None

    def json(self):
        if self.invalid_json:
            raise ValueError("invalid")
        return self.payload


class FakeGoongClient:
    def __init__(self, detail_invalid=False):
        self.calls = []
        self.detail_invalid = detail_invalid

    def get(self, url, params):
        self.calls.append((url, params))
        if url.endswith("/Place/AutoComplete"):
            return FakeResponse({
                "predictions": [{
                    "place_id": "goong-place-id",
                    "description": "Chợ Bến Thành, Thành phố Hồ Chí Minh",
                    "structured_formatting": {
                        "main_text": "Chợ Bến Thành",
                        "secondary_text": "Thành phố Hồ Chí Minh",
                    },
                }],
                "status": "OK",
            })
        return FakeResponse({
            "result": {
                "place_id": "goong-place-id",
                "formatted_address": "Chợ Bến Thành, Quận 1, Thành phố Hồ Chí Minh",
                "geometry": {"location": {"lat": 10.7725, "lng": 106.698}},
                "name": "Chợ Bến Thành",
                "types": ["point_of_interest"],
            },
            "status": "OK",
        }, invalid_json=self.detail_invalid)


def test_goong_autocomplete_and_detail_keep_generic_map_contract():
    client = FakeGoongClient()
    tool = GoongPlacesTool("secret-key", client=client)

    result = tool.run("Chợ Bến Thành", limit=1)
    payload = json.loads(result.content)
    place = payload["places"][0]

    assert result.success is True
    assert payload["provider"] == "goong"
    assert place["location"] == {"latitude": 10.7725, "longitude": 106.698}
    assert place["geo_uri"] == "geo:10.7725,106.698"
    assert place["map_url"].startswith("https://www.openstreetmap.org/")
    assert client.calls[0][0].endswith("/Place/AutoComplete")
    assert client.calls[0][1]["input"] == "Chợ Bến Thành"
    assert client.calls[0][1]["limit"] == 1
    assert client.calls[1][0].endswith("/Place/Detail")
    assert client.calls[1][1]["place_id"] == "goong-place-id"
    assert client.calls[1][1]["sessiontoken"] == client.calls[0][1]["sessiontoken"]
    assert "secret-key" not in result.content


def test_goong_detail_failure_preserves_autocomplete_prediction():
    tool = GoongPlacesTool("key", client=FakeGoongClient(detail_invalid=True))

    payload = json.loads(tool.run("Chợ Bến Thành", limit=1).content)
    place = payload["places"][0]

    assert place["name"] == "Chợ Bến Thành"
    assert place["address"] == "Chợ Bến Thành, Thành phố Hồ Chí Minh"
    assert place["location"] is None
    assert "warning" in place


def test_goong_tool_is_unavailable_without_key():
    assert GoongPlacesTool("").spec.available is False

