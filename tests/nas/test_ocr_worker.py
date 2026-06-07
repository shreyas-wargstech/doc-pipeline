"""Unit test for the local OCR worker's single drain cycle.

A fake async SQS client returns two messages; process_record is monkeypatched
to succeed for one and raise for the other. Assert: the succeeded message is
deleted, the failed one is left in the queue for redelivery."""
from __future__ import annotations

import scripts.run_ocr_worker as worker


class _FakeSQS:
    def __init__(self, messages):
        self._messages = messages
        self.deleted: list[str] = []

    async def receive_message(self, **kwargs):
        return {"Messages": self._messages}

    async def delete_message(self, *, QueueUrl, ReceiptHandle):  # noqa: N803
        self.deleted.append(ReceiptHandle)


async def test_drain_once_deletes_only_successful(monkeypatch):
    messages = [
        {"MessageId": "ok", "Body": "{}", "ReceiptHandle": "rh-ok"},
        {"MessageId": "bad", "Body": "{}", "ReceiptHandle": "rh-bad"},
    ]

    # Make process deterministic: succeed first call, fail second.
    calls = {"n": 0}

    async def fake_process2(body, *, router=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")

    monkeypatch.setattr(worker, "process_record", fake_process2)
    sqs = _FakeSQS(messages)

    processed, failed = await worker.drain_once(sqs, "q-url", router=None)

    assert processed == 1
    assert failed == 1
    assert sqs.deleted == ["rh-ok"]  # only the successful one deleted


async def test_drain_once_no_messages(monkeypatch):
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(worker, "process_record", _noop)
    sqs = _FakeSQS([])
    processed, failed = await worker.drain_once(sqs, "q-url", router=None)
    assert (processed, failed) == (0, 0)
