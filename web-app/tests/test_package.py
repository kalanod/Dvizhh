from importlib.resources import files


def test_package_import() -> None:
    import dvizh_web

    assert dvizh_web.__doc__


def test_static_index_is_packaged() -> None:
    assert files("dvizh_web").joinpath("static/index.html").is_file()
