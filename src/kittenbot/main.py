from pymorphy3.analyzer import MorphAnalyzer
from sqlalchemy import create_engine
from telegram.ext import ApplicationBuilder, filters, CommandHandler, MessageHandler

from . import entities
from .admin_handler import get_user_id_handler, SlowCommandHandler
from .clock import ProdClock
from .config import BotConfig
from .pipelines import pipeline, slowmode_support
from .message_handler import KittenMessageHandler
from .history import History
from .interpreter import Interpreter
from .language_processing import Nlp
from .permissions import allow_all, whitelist
from .ping_handler import ping
from .random_generator import RandomGenerator
from .resources import ProdResources
from .slowmode_user_repository import SlowmodeUserRepository
from .middleware import StoringUpdateProcessorWrapper


def main():
    config = BotConfig()
    if config.token is None:
        print("Token is not set, exit")
        exit(1)

    engine = create_engine(config.db_connection_string)
    entities.User.metadata.create_all(engine, checkfirst=True)
    entities.Chat.metadata.create_all(engine, checkfirst=True)
    entities.chat_users.metadata.create_all(engine, checkfirst=True)
    entities.SlowmodeUser.metadata.create_all(engine, checkfirst=True)

    hist = History(engine)
    rand_gen = RandomGenerator()
    resources = ProdResources(rand_gen, "resources")
    self_user_id = int(config.token.split(":")[0])
    message_handler = KittenMessageHandler(
        rand_gen,
        resources,
        Nlp(MorphAnalyzer()),
        self_user_id,
        config.probability,
        config.agree_probability,
        config.test_group_ids,
        config.bot_names,
        config.noun_template,
    )

    app = (ApplicationBuilder()
           .concurrent_updates(StoringUpdateProcessorWrapper(hist))
           .token(config.token)
           .build())

    interpreter = Interpreter(app.bot)
    security = whitelist(config.admin_user_ids)
    clock = ProdClock()
    slowmode_user_repository = SlowmodeUserRepository(engine, clock)
    slow_handler = SlowCommandHandler(slowmode_user_repository, hist, clock)
    app.add_handlers([
        CommandHandler("ping", pipeline(allow_all, ping, interpreter)),
        CommandHandler("get_user_id", pipeline(security, get_user_id_handler(hist), interpreter)),
        CommandHandler("slow", pipeline(security, slow_handler, interpreter)),
        MessageHandler(
            ~filters.COMMAND,
            pipeline(allow_all, slowmode_support(slowmode_user_repository, clock)(message_handler), interpreter)),
    ])
    print("Bot is listening")
    app.run_polling()
