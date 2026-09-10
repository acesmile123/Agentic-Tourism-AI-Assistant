from tourism_agent.services.generation import ModelRouter


def test_model_router_uses_fast_model_for_simple_question():
    router = ModelRouter("fast", "complex")
    assert router.select("Ăn phở ngon ở đâu tại Hà Nội?") == "fast"


def test_model_router_uses_complex_model_for_itinerary():
    router = ModelRouter("fast", "complex")
    assert router.select("Lập lịch trình ba ngày ở Đà Nẵng") == "complex"

