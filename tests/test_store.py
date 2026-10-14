import json

import pytest

from shtorka.store import BrokenFile, Store, Template, search


@pytest.fixture
def store(tmp_path, qapp):
    return Store(tmp_path / "templates.json")


def test_missing_file_is_empty(store):
    assert store.load() == []


def test_save_sorts_and_replaces(store):
    store.save(Template("бета", "2"))
    alpha = Template("Альфа", "1")
    store.save(alpha)
    alpha.text = "один"
    store.save(alpha)
    assert [(t.title, t.text) for t in store.load()] == [("Альфа", "один"), ("бета", "2")]


def test_delete(store):
    keep, drop = Template("a", "1"), Template("b", "2")
    store.save(keep)
    store.save(drop)
    store.delete(drop)
    assert [t.id for t in store.load()] == [keep.id]


def test_hand_written_entries_get_stable_ids(store):
    store.path.write_text(json.dumps([{"title": "Привет", "text": "Здравствуйте"}]), encoding="utf-8")
    first, second = store.load(), store.load()
    assert first[0].id and first[0].id == second[0].id


@pytest.mark.parametrize("content", ["[{", '{"title": "x"}', '[{"title": "x"}]', '["text"]'])
def test_broken_file_is_never_overwritten(store, content):
    store.path.write_text(content, encoding="utf-8")
    assert store.load() == []
    with pytest.raises(BrokenFile):
        store.save(Template("новый", "текст"))
    with pytest.raises(BrokenFile):
        store.delete(Template("новый", "текст"))
    assert store.path.read_text(encoding="utf-8") == content


def test_blank_file_is_empty(store):
    store.path.write_text("\n", encoding="utf-8")
    store.save(Template("a", "1"))
    assert len(store.load()) == 1


def test_write_leaves_no_temp_file(store):
    store.save(Template("a", "1"))
    assert [p.name for p in store.path.parent.iterdir()] == ["templates.json"]


TEMPLATES = [
    Template("Приветствие", "Здравствуйте! Чем могу помочь?"),
    Template("Сроки доставки", "Доставка занимает 2–3 рабочих дня."),
    Template("Ещё вопрос", "Остались вопросы по доставке?"),
]


def titles(found):
    return [t.title for t in found]


def test_search_without_query_keeps_everything():
    assert titles(search(TEMPLATES, "  ")) == titles(TEMPLATES)


def test_search_puts_title_matches_first():
    assert titles(search(TEMPLATES, "ДОСТ")) == ["Сроки доставки", "Ещё вопрос"]


def test_search_needs_every_word():
    assert titles(search(TEMPLATES, "срок дост")) == ["Сроки доставки"]
    assert search(TEMPLATES, "срок оплаты") == []


def test_search_treats_yo_as_ye():
    assert titles(search(TEMPLATES, "еще")) == ["Ещё вопрос"]
