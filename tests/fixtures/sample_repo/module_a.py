from __future__ import absolute_import


def do_periodic_idle(logger):
    # Exact-match line for the demo and unit tests:
    logger.error("PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE")

    # Near misses / variations:
    logger.error("periodicidle: waitcomplete for localhost:9210:dyn-ultron:valve")  # normalized/casing
    logger.error("PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron")  # missing tail token
    logger.info("EngineConductor: Changing state from IDLE to SERVICING")  # unrelated


def do_periodic_idle_second(logger):
    # Same message appears in a different function (for analyzer multi-hit tests):
    logger.error("OtherComponent: waitComplete for localhost:9210:Dyn-ultron:VALVE")


