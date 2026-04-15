import importlib.util
import os
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"


def load_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyMarkup:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.items = []

    def add(self, *items):
        self.items.extend(items)


class DummyButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class FakeBot:
    def __init__(self):
        self.sent_messages = []
        self.next_steps = []
        self.message_handlers = []
        self.callback_handlers = []

    def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append((chat_id, text, kwargs))
        return types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), message_id=len(self.sent_messages))

    def register_next_step_handler(self, msg, handler, *args):
        self.next_steps.append((msg, handler, args))

    def message_handler(self, commands=None, func=None):
        def decorator(handler):
            self.message_handlers.append({"commands": commands, "func": func, "handler": handler})
            return handler
        return decorator

    def callback_query_handler(self, func=None):
        def decorator(handler):
            self.callback_handlers.append({"func": func, "handler": handler})
            return handler
        return decorator

    def reply_to(self, message, text, **kwargs):
        self.sent_messages.append((message.chat.id, text, kwargs))

    def answer_callback_query(self, *args, **kwargs):
        pass

    def edit_message_text(self, *args, **kwargs):
        pass

    def set_my_commands(self, commands):
        pass

    def find_handler(self, *, text=None, command=None):
        for item in self.message_handlers:
            if command and item["commands"] and command in item["commands"]:
                return item["handler"]
            if text and item["func"] and item["func"](types.SimpleNamespace(text=text)):
                return item["handler"]
        raise AssertionError(f"Handler not found for text={text!r} command={command!r}")


class DelayRecorder:
    def __init__(self):
        self.calls = []

    def delay(self, *args):
        self.calls.append(args)


def load_telebot_module(monkeypatch):
    fake_types = types.SimpleNamespace(
        ReplyKeyboardMarkup=DummyMarkup,
        InlineKeyboardMarkup=DummyMarkup,
        KeyboardButton=DummyButton,
        InlineKeyboardButton=DummyButton,
        BotCommand=DummyButton,
    )
    portal_task = DelayRecorder()
    deadline_task = DelayRecorder()
    status_task = DelayRecorder()
    registration_task = DelayRecorder()
    custom_deadline_task = DelayRecorder()

    monkeypatch.setitem(sys.modules, "telebot", types.SimpleNamespace(types=fake_types))
    monkeypatch.setitem(
        sys.modules,
        "utils",
        types.SimpleNamespace(
            os=os,
            startStepTimeout=lambda *args, **kwargs: None,
            cancelStepTimeout=lambda *args, **kwargs: None,
            log=lambda *args, **kwargs: None,
        ),
    )
    monkeypatch.setitem(sys.modules, "teleFunc", types.SimpleNamespace(handleToggleNotify=lambda chat_id: (True, "ok"), handleToggleDeadlineNotify=lambda chat_id: (True, "ok"), handleSendFeedback=lambda *args, **kwargs: None, getAdminStats=lambda admin_id: "stats", broadcastToAllUsers=lambda *args, **kwargs: 0))
    monkeypatch.setitem(sys.modules, "database", types.SimpleNamespace(markTaskCompleted=lambda *args, **kwargs: True, unmarkTaskCompleted=lambda *args, **kwargs: True))
    monkeypatch.setitem(sys.modules, "cronService", types.SimpleNamespace(autoCheckAndNotify=lambda bot: None, autoScanAllUsers=lambda bot: None))
    monkeypatch.setitem(
        sys.modules,
        "task",
        types.SimpleNamespace(
            portalTask=portal_task,
            deadlineTask=deadline_task,
            systemStatusTask=status_task,
            registrationTask=registration_task,
            customDeadlineTask=custom_deadline_task,
        ),
    )

    module = load_module("test_telebot_module", SOURCE_DIR / "teleBot.py")
    return module, {
        "portalTask": portal_task,
        "deadlineTask": deadline_task,
        "systemStatusTask": status_task,
        "registrationTask": registration_task,
        "customDeadlineTask": custom_deadline_task,
    }


def test_menu_handlers_dispatch_without_progress_messages(monkeypatch):
    telebot_module, tasks = load_telebot_module(monkeypatch)
    bot = FakeBot()
    telebot_module.registerHandlers(bot)
    message = types.SimpleNamespace(chat=types.SimpleNamespace(id=123), text=None)

    bot.find_handler(text="📅 Lịch hôm nay")(types.SimpleNamespace(chat=message.chat, text="📅 Lịch hôm nay"))
    bot.find_handler(text="⏭️ Lịch ngày mai")(types.SimpleNamespace(chat=message.chat, text="⏭️ Lịch ngày mai"))
    bot.find_handler(text="📑 Quét deadline")(types.SimpleNamespace(chat=message.chat, text="📑 Quét deadline"))
    bot.find_handler(text="🛠️ Kiểm tra hệ thống")(types.SimpleNamespace(chat=message.chat, text="🛠️ Kiểm tra hệ thống"))

    assert bot.sent_messages == []
    assert tasks["portalTask"].calls[0][0] == 123
    assert tasks["portalTask"].calls[1][0] == 123
    assert tasks["deadlineTask"].calls == [(123,)]
    assert tasks["systemStatusTask"].calls == [(123,)]


def test_followup_steps_dispatch_without_progress_messages(monkeypatch):
    telebot_module, tasks = load_telebot_module(monkeypatch)
    bot = FakeBot()
    message = types.SimpleNamespace(chat=types.SimpleNamespace(id=456), text="secret")

    telebot_module.processPasswordStep(message, bot, "21520001")
    assert bot.sent_messages == []
    assert tasks["registrationTask"].calls == [(456, "21520001", "secret")]

    date_message = types.SimpleNamespace(chat=types.SimpleNamespace(id=456), text="20/04/2026")
    telebot_module.processCustomDate(date_message, bot)
    assert bot.sent_messages == []
    assert tasks["portalTask"].calls == [(456, "20/04/2026")]

    days_message = types.SimpleNamespace(chat=types.SimpleNamespace(id=456), text="14")
    telebot_module.processDaysStep(days_message, "20/04/2026", bot)
    assert bot.sent_messages == []
    assert tasks["customDeadlineTask"].calls == [(456, "20/04/2026", 14)]


def test_send_worker_check_in_does_not_message_user(monkeypatch):
    fake_bot = types.SimpleNamespace(send_message=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not send progress message")))
    monkeypatch.setitem(sys.modules, "celeryApp", types.SimpleNamespace(app=types.SimpleNamespace(task=lambda *args, **kwargs: (lambda fn: fn))))
    monkeypatch.setitem(sys.modules, "telebot", types.SimpleNamespace(TeleBot=lambda token: fake_bot))
    monkeypatch.setitem(sys.modules, "courseService", types.SimpleNamespace(scanAllDeadlines=lambda *args, **kwargs: None))
    monkeypatch.setitem(sys.modules, "portalService", types.SimpleNamespace(formatCalendarMessage=lambda *args, **kwargs: None, verifyAndSaveUser=lambda *args, **kwargs: (True, "ok")))
    monkeypatch.setitem(sys.modules, "teleFunc", types.SimpleNamespace(getSystemStatus=lambda *args, **kwargs: None))
    monkeypatch.setitem(sys.modules, "redisManager", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "utils", types.SimpleNamespace(log=lambda *args, **kwargs: None, safeRequest=lambda *args, **kwargs: None))

    task_module = load_module("test_task_module", SOURCE_DIR / "task.py")
    fake_self = types.SimpleNamespace(request=types.SimpleNamespace(hostname="VIP_Worker"))

    task_module.sendWorkerCheckIn(fake_self, 789)
