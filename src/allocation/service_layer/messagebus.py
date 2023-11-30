from __future__ import annotations
from typing import List, Dict, Callable, Type, TYPE_CHECKING, Union
from allocation.domain import events, commands
import logging
from . import handlers
from tenacity import Retrying, RetryError, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from . import unit_of_work

Message = Union[commands.Command, events.Event]

def handle(
    message: commands,
    uow: unit_of_work.AbstractUnitOfWork,
):
    results = []
    queue = [message]
    while queue:
        message = queue.pop(0)
        if isinstance(message, events.Event):
            handle_event(message, queue, uow)
        elif isinstance(message, commands.Command):
            cmd_result = handle_command(message, queue, uow)
            results.append(cmd_result)
        else:
            raise Exception(f"{message} was not not an Event or Command")
    return results



def handle_event(
        event: events.Event, 
        queue: List[Message], 
        uow: unit_of_work.AbstractUnitOfWork):
    for handler in EVENT_HANDLERS[type(event)]:
        try:
            for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_exponential()):
                with attempt:
                    logger.debug('handling event %s with handler %s', event, handle)
                    handler(event, uow)
                    queue.extend(uow.collect_new_events())
        except RetryError as retry_failure:
            logger.error("Failed to handle event %s for %s times, givin up", event, retry_failure.last_attempt.attempt_number)
            continue


def handle_command(
        command: commands.Command, 
        queue: List[Message],
        uow: unit_of_work.AbstractUnitOfWork):
    logger.debug("handling command %s", command)
    try:
        handler = COMMAND_HANDLERS[type(command)]
        result = handler(command, uow)
        queue.extend(uow.collect_new_events())
        return result
    except Exception:
        logger.exception('Exception handling command %s', command)
        raise


EVENT_HANDLERS = {
    events.OutOfStock: [handlers.send_out_of_stock_notification],
}  # type: Dict[Type[events.Event], List[Callable]]

COMMAND_HANDLERS = {
    commands.CreateBatch: handlers.add_batch,
    commands.ChangeBatchQuantity: handlers.change_batch_quantity,
    commands.Allocate: handlers.allocate,
}  # type: Dict[Type[events.Event], List[Callable]]

