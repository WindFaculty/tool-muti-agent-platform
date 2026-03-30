from __future__ import annotations

import pytest

from app.profiles.notepad_profile import NotepadProfile


class TestNotepadProfileParser:
    def setup_method(self):
        self.profile = NotepadProfile()

    def test_type_and_save_plain(self, tmp_path):
        plan = self.profile.build_plan("type hello world and save", tmp_path)
        names = [a.name for a in plan]
        assert "open_new_document" in names
        assert "type_in_editor" in names
        assert "confirm_save" in names

    def test_type_and_save_with_path(self, tmp_path):
        task = f"type hello and save to {tmp_path / 'out.txt'}"
        plan = self.profile.build_plan(task, tmp_path)
        save_action = next(a for a in plan if a.name == "confirm_save")
        assert "out.txt" in str(save_action.metadata.get("save_path", ""))

    def test_clear_and_type(self, tmp_path):
        plan = self.profile.build_plan("clear and type fresh content and save", tmp_path)
        names = [a.name for a in plan]
        assert "select_all" in names
        assert "delete_selection" in names
        assert "type_in_editor" in names

    def test_append(self, tmp_path):
        plan = self.profile.build_plan("append more text and save", tmp_path)
        names = [a.name for a in plan]
        assert "move_to_end" in names
        assert "type_append" in names

    def test_open_new(self, tmp_path):
        plan = self.profile.build_plan("open new", tmp_path)
        assert len(plan) == 1
        assert plan[0].name == "open_new_document"

    def test_unsupported_task_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported notepad task"):
            self.profile.build_plan("do something else entirely", tmp_path)
