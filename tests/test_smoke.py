import engine
import report


def test_packages_import():
    assert engine.__name__ == "engine"
    assert report.__name__ == "report"
