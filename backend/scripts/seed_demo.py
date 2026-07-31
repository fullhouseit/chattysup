"""Populate an installation with demo data.

    cd backend && python scripts/seed_demo.py

Creates an admin (demo@chattysup.local / demo1234), a Telegram inbox in polling
mode, a handful of contacts and conversations with realistic message history.
Safe to re-run: it does nothing when conversations already exist.
"""
from __future__ import annotations

import asyncio
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal, init_db, utcnow  # noqa: E402
from app.models import (  # noqa: E402
    Contact,
    ContactInbox,
    Conversation,
    ConversationLabel,
    Inbox,
    Label,
    Message,
    User,
)
from app.services.settings_service import seed_defaults  # noqa: E402

CONTACTS = [
    ("Klaus Crawley", "kcrawley6@driftburner.inc", "+14155552398", "Drift Burner",
     "Founder", "San Francisco, United States", "device-setup",
     "Hi, I need some help setting up my new device."),
    ("Candice Matherson", "candice@northpeak.io", "+14155550119", "Northpeak",
     "Head of Ops", "Austin, United States", "lead",
     "Hey, do you have a plan for teams of 20+?"),
    ("Coreen Mewett", "coreen.m@lumenlabs.co", "+442071838001", "Lumen Labs",
     "Designer", "London, United Kingdom", "software",
     "The mobile app keeps logging me out every hour."),
    ("Quent Dalliston", "quent@fieldbase.dev", "+61255501877", "Fieldbase",
     "CTO", "Sydney, Australia", "software",
     "Can you share the API docs for the webhooks?"),
    ("Nathaniel Vannuchi", "nathaniel@brightfold.com", "+13125550144", "Brightfold",
     "Finance", "Chicago, United States", "billing",
     "There, I need some help with billing — I was charged twice."),
    ("Merrile Petruk", "merrile@havenway.se", "+46812345678", "Havenway",
     "Support Lead", "Stockholm, Sweden", "device-setup",
     "My scanner will not pair with the hub."),
]

REPLIES = [
    "No problem! Can you please tell me the make and model of your device and what "
    "specifically you need help with?",
    "Thanks for reaching out — let me check that for you.",
    "I've escalated this to our engineering team, I'll keep you posted.",
]


async def main() -> None:
    await init_db()
    async with SessionLocal() as db:
        await seed_defaults(db)

        admin = await db.scalar(select(User).limit(1))
        if admin is None:
            admin = User(
                name="Demo Admin",
                email="demo@chattysup.local",
                password_hash=hash_password("demo1234"),
                role="admin",
                availability="online",
            )
            db.add(admin)
            await db.flush()

        if await db.scalar(select(func.count(Conversation.id))):
            print("Demo data already present — nothing to do.")
            return

        inbox = await db.scalar(select(Inbox).where(Inbox.channel_type == "telegram"))
        if inbox is None:
            inbox = Inbox(
                name="ChattySup Telegram",
                channel_type="telegram",
                mode="polling",
                config={"bot_token": "000000:demo-token", "download_media": True},
                greeting_enabled=True,
                greeting_message="Hi {{contact.first_name}} 👋, how may I help you?",
                connection_status="unknown",
            )
            db.add(inbox)
            await db.flush()

        labels = {
            label.title: label for label in (await db.scalars(select(Label))).all()
        }

        for index, (name, email, phone, company, title, location, label, opener) in enumerate(
            CONTACTS
        ):
            # Old conversation, recent activity — reads as "3mo • 25m" in the list.
            created = utcnow() - timedelta(days=90 - index * 3, minutes=index * 17)
            last_seen = utcnow() - timedelta(minutes=25 + index * 47)
            contact = Contact(
                name=name,
                email=email,
                phone=phone,
                company=company,
                title=title,
                location=location,
                identifier=name.split(" ")[0].lower(),
                last_activity_at=last_seen,
                custom_attributes={"plan": random.choice(["free", "pro", "scale"])},
            )
            db.add(contact)
            await db.flush()

            link = ContactInbox(
                contact_id=contact.id,
                inbox_id=inbox.id,
                source_id=str(700000 + contact.id),
                meta={"chat_type": "private"},
            )
            db.add(link)
            await db.flush()

            conversation = Conversation(
                inbox_id=inbox.id,
                contact_id=contact.id,
                contact_inbox_id=link.id,
                source_id=link.source_id,
                status="open" if index % 3 else "pending",
                priority=("high" if index == 0 else "urgent" if index == 4 else "none"),
                assignee_id=admin.id if index % 2 == 0 else None,
                created_at=created,
                last_activity_at=last_seen,
                unread_count=1 if index % 2 else 0,
                greeting_sent=True,
            )
            db.add(conversation)
            await db.flush()

            if label in labels:
                db.add(
                    ConversationLabel(
                        conversation_id=conversation.id, label_id=labels[label].id
                    )
                )

            db.add(
                Message(
                    conversation_id=conversation.id,
                    inbox_id=inbox.id,
                    content=opener,
                    message_type="incoming",
                    sender_type="contact",
                    sender_id=contact.id,
                    source_id=f"{conversation.id}-1",
                    status="delivered",
                    created_at=last_seen,
                )
            )
            db.add(
                Message(
                    conversation_id=conversation.id,
                    inbox_id=inbox.id,
                    content=REPLIES[index % len(REPLIES)],
                    message_type="outgoing",
                    sender_type="user",
                    sender_id=admin.id,
                    source_id=f"{conversation.id}-2",
                    status="sent",
                    created_at=last_seen + timedelta(minutes=2),
                )
            )
            if index == 0:
                db.add(
                    Message(
                        conversation_id=conversation.id,
                        inbox_id=inbox.id,
                        content="Checked the logs — the device firmware is out of date.",
                        message_type="outgoing",
                        sender_type="user",
                        sender_id=admin.id,
                        private=True,
                        status="sent",
                        created_at=last_seen + timedelta(minutes=5),
                    )
                )
                db.add(
                    Message(
                        conversation_id=conversation.id,
                        inbox_id=inbox.id,
                        content=f"{admin.name} set the priority to high",
                        message_type="activity",
                        content_type="system",
                        sender_type="system",
                        created_at=last_seen + timedelta(minutes=6),
                    )
                )

        await db.commit()
        print("Seeded demo data — sign in as demo@chattysup.local / demo1234")


if __name__ == "__main__":
    asyncio.run(main())
