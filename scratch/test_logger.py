import time
import threading
import warnings
from studio_logger import logger

def test_spam():
    logger.info("Starting spam test...")
    for i in range(250):
        logger.error("Este es un error que se repite muchísimas veces")
    logger.info("Spam test finished. Should have printed only a few times.")

def test_warning():
    logger.info("Starting warning test...")
    warnings.warn("Esta es una advertencia de Python que debería ser capturada por el logger", DeprecationWarning)

def thread_crash():
    time.sleep(1)
    raise ValueError("El hilo secundario explotó")

def test_thread_exception():
    logger.info("Starting thread exception test...")
    t = threading.Thread(target=thread_crash, name="CrashThread")
    t.start()
    t.join()

def test_global_exception():
    logger.info("Starting global exception test...")
    raise ZeroDivisionError("División por cero no manejada en el hilo principal")

if __name__ == "__main__":
    test_spam()
    test_warning()
    test_thread_exception()
    test_global_exception()
