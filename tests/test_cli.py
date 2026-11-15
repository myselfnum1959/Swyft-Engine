from swyft.__main__ import main


def test_check_reports_ok_and_errors(tmp_path, capsys):
    good = tmp_path / "good.swy"
    good.write_text('label start:\n    "hi"\n')
    bad = tmp_path / "bad.swy"
    bad.write_text("label start:\n    jump nowhere\n")
    assert main(["check", str(good)]) == 0
    assert "OK" in capsys.readouterr().out
    assert main(["check", str(bad)]) == 1
    assert "bad.swy:2" in capsys.readouterr().out
    assert main(["check", str(tmp_path / "missing.swy")]) == 1
    assert main([]) == 2
