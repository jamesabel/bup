from bup.gui.gui_icon import get_icon_path


def test_get_icon_path_png():
    path = get_icon_path("png")
    assert path.name == "bup.png"
    assert path.exists()


def test_get_icon_path_ico():
    path = get_icon_path("ico")
    assert path.name == "bup.ico"
    assert path.exists()


def test_get_icon_path_missing():
    path = get_icon_path("xyz")
    assert path.name == "bup.xyz"
    assert not path.exists()
