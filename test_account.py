from IGBot.core.account import Account
from IGBot.core.session_engine import SessionEngine

account = Account(
    username="its_madisonparker",
    device_id="R5CR61HA38V",
    app_id="com.instagram.androie",
)

engine = SessionEngine(account)

engine.start()
print(engine.status())
engine.stop()
print(engine.status())
