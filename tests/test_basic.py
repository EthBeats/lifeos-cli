from typer.testing import CliRunner
from lifeos.cli.main import app

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "LifeOS CLI" in result.output
