# Goong provider for `map_location`

`map_location` giữ nguyên tên và MCP contract nên Agent workflow không đổi. Provider phía sau là Goong Places.

## API flow

```text
map_location(query, limit)
  -> GET /Place/AutoComplete  # lấy predictions + place_id
  -> GET /Place/Detail        # lấy tên, địa chỉ và tọa độ
  -> normalized ToolResult
```

Mỗi lần gọi tool tạo một UUID `sessiontoken` và dùng chung token cho AutoComplete và Place Detail. Mặc định `limit=1`; tăng limit sẽ tạo thêm một Place Detail request cho mỗi prediction được chọn.

## Configuration

Tạo **REST API Key** trong Goong Account, không dùng Maptiles Key, rồi thêm vào `.env`:

```env
GOONG_API_KEY=your-rest-api-key
GOONG_BASE_URL=https://rsapi.goong.io
```

`VIETMAP_API_KEY`, `VIETMAP_BASE_URL` và `GOOGLE_MAPS_API_KEY` không còn được code đọc. Có thể xóa chúng khỏi `.env` nếu không còn ứng dụng khác sử dụng.

Sau khi đổi `.env`:

```powershell
docker compose up -d --build --force-recreate mcp api
docker compose logs -f mcp api
```

## Normalized output

```json
{
  "provider": "goong",
  "query": "Chợ Bến Thành",
  "result_count": 1,
  "places": [
    {
      "name": "Chợ Bến Thành",
      "address": "...",
      "location": {"latitude": 10.7725, "longitude": 106.698},
      "place_id": "...",
      "types": [],
      "geo_uri": "geo:10.7725,106.698",
      "map_url": "https://www.openstreetmap.org/..."
    }
  ]
}
```

Goong cung cấp dữ liệu tìm kiếm, địa chỉ và tọa độ. `map_url` là link OpenStreetMap được tạo từ tọa độ để người dùng có thể mở mà không cần lộ REST API key. Tool không trả API key, rating hoặc website.

Tài liệu API: https://docs.goong.io/rest/place/

