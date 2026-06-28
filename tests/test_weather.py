from app.services.weather import _demo_weather


def test_demo_weather_is_labelled_and_complete() -> None:
    weather = _demo_weather(11.2, 10.8, "Northern Gombe", "test")
    assert weather.mode == "demo"
    assert weather.location_name == "Northern Gombe"
    assert 0 <= weather.humidity_percent <= 100
    assert weather.wind_speed_mps >= 0
    assert weather.sunrise < weather.sunset
    assert "not an observation" in weather.note.lower()
