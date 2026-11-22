import os
import subprocess
import sys
import pytest
from prices_analyzer.cli import main
from prices_analyzer import database


def test_help_and_invalid_arguments(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['--help'])
    assert exc.value.code == 0
    assert 'ПЕРЕД командой' in capsys.readouterr().out
    for args in ([], ['compare','--product','demo:x','--quantity','0','--max-days','7'],
                 ['collect','books','--max-pages','0'],['import-html','x.html'],
                 ['list','--db','wrong-position.sqlite3']):
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2


def test_cli_import_history_and_partial_code(tmp_path,backend,capsys):
    db = tmp_path/'cli.sqlite3'
    prefix = ['--db',str(db)]
    assert main(prefix+['init-db']) == 0
    assert main(prefix+['import-csv',str(backend/'data/sample_offers.csv')]) == 0
    assert main(prefix+['import-csv',str(backend/'data/sample_offers.csv')]) == 0
    assert 'пропущено как дубликаты: 8' in capsys.readouterr().out
    assert main(prefix+['history','--source','demo','--offer','paper-b']) == 0
    text = capsys.readouterr().out
    assert '120 RUB' in text and '125 RUB' in text
    assert main(prefix+['import-csv',str(backend/'data/invalid_offers.csv')]) == 1
    assert 'Строка 3' in capsys.readouterr().err
    assert main(['--db',str(tmp_path/'missing.sqlite3'),'list']) == 2


def test_demo_safe_repeat_and_user_db_untouched(tmp_path,capsys):
    user = tmp_path/'user.sqlite3'
    user.write_bytes(b'not a demo database')
    folder = tmp_path/'demo-folder'
    for _ in range(2):
        assert main(['--db',str(user),'demo','--directory',str(folder)]) == 0
        text = capsys.readouterr().out
        assert 'добавлено: 8' in text and 'пропущено как дубликаты: 8' in text
        assert '1300 RUB' in text and 'надёжно выбрать' in text
        assert user.read_bytes() == b'not a demo database'
        assert list(folder.iterdir()) == []


def test_module_entrypoint_and_reopen(tmp_path,backend):
    env = {**os.environ,'PYTHONIOENCODING':'utf-8'}
    db = tmp_path/'process.sqlite3'
    def run(*args):
        return subprocess.run([sys.executable,'-m','prices_analyzer','--db',str(db),*args],
            cwd=backend,env=env,text=True,encoding='utf-8',capture_output=True,timeout=15)
    assert run('init-db').returncode == 0
    assert run('import-csv','data/sample_offers.csv').returncode == 0
    result = run('list','--product','demo:paper-a4')
    assert result.returncode == 0 and 'Учебная бумага' in result.stdout
    assert len(database.latest(db)) == 7
