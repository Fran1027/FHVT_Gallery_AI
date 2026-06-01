import logging
import time
import threading
import os
import sys
import re
from functools import wraps


class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# Compilar el Regex una sola vez a nivel global para optimizar rendimiento de CPU
ANSI_REGEX = re.compile(r"\033\[[0-9;]*m")


class LogcatFormatter(logging.Formatter):
    """Imita la estructura: Hora | Thread | Nivel | Tag: Mensaje"""

    def __init__(self, use_colors=True):
        super().__init__()
        self.use_colors = use_colors

    def format(self, record):
        timestamp = self.formatTime(record, "%H:%M:%S")
        thread_name = threading.current_thread().name

        # 1. Determinar el "Tag" dinámico de forma robusta
        if hasattr(record, "classname"):
            tag = f"{record.classname}:{record.funcName}"
        else:
            # Fallback inteligente si se llama a logger.info directo sin decorador
            tag = f"{os.path.basename(record.pathname)}:{record.funcName}"

        lvl = record.levelname[:1]

        if self.use_colors:
            # Formato con Estilo ANSI para Consola
            thread_color = Colors.PURPLE if thread_name == "MainThread" else Colors.GRAY
            level_colors = {
                logging.DEBUG: Colors.GRAY,
                logging.INFO: Colors.GREEN,
                logging.WARNING: Colors.YELLOW,
                logging.ERROR: Colors.RED,
                logging.CRITICAL: Colors.BOLD + Colors.RED,
            }
            c = level_colors.get(record.levelno, Colors.RESET)

            header = f"{Colors.GRAY}{timestamp}{Colors.RESET} | {thread_color}{thread_name[:10]:>10}{Colors.RESET} | {c}{lvl}{Colors.RESET} | {Colors.CYAN}{tag}{Colors.RESET}: "
        else:
            # Formato Limpio de texto plano para el archivo .log
            header = f"{timestamp} | {thread_name[:10]:>10} | {lvl} | {tag}: "

        message = record.getMessage()

        # Si la traza incluye un error completo (Traceback), lo formateamos
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                message = f"{message}\n{record.exc_text}"

        # Manejo multilínea respetando la indentación del header
        if "\n" in message:
            indent_len = (
                len(ANSI_REGEX.sub("", header)) if self.use_colors else len(header)
            )
            message = message.replace("\n", "\n" + " " * indent_len)

        return f"{header}{message}"


def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_logger():
    logger = logging.getLogger("FHVT_gallery")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Handler 1: Consola (Con colores ANSI vivos)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(LogcatFormatter(use_colors=True))
        logger.addHandler(console_handler)

        # Handler 2: Archivo Físico (Texto plano limpio para auditoría post-mortem)
        try:
            log_dir = os.path.join(get_base_path(), "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "fhvt_session.log")

            # Usamos modo 'w' para limpiar el log en cada inicio, o 'a' si prefieres historial
            file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
            file_handler.setFormatter(LogcatFormatter(use_colors=False))
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)

            # Inicializar faulthandler para capturar crashes de bajo nivel (como en torch_cpu.dll)
            try:
                import faulthandler

                crash_log = os.path.join(log_dir, "fhvt_crash.log")
                # Mantenemos una referencia global al archivo para que no se cierre por GC
                global _crash_file_handle
                _crash_file_handle = open(crash_log, "w", encoding="utf-8")
                faulthandler.enable(file=_crash_file_handle, all_threads=True)
            except Exception as fe:
                logger.warning(
                    f"No se pudo habilitar faulthandler para fallos físicos: {str(fe)}"
                )

        except Exception as e:
            logger.warning(
                f"No se pudo inicializar el archivo de logs en disco: {str(e)}"
            )

    return logger


logger = setup_logger()


def log_action(arg):
    """Decorador Avanzado: Captura duración, clase, hilos y errores con Traceback completo."""

    def actual_decorator(func, msg=None):
        @wraps(func)
        def wrapper(*args, **kwargs):
            classname = (
                args[0].__class__.__name__
                if args and hasattr(args[0], "__class__")
                else "Global"
            )
            start_time = time.perf_counter()
            display_msg = msg if msg else f"Invoke {func.__name__}"

            logger.info(
                f"{Colors.BOLD}{display_msg}{Colors.RESET}",
                extra={"classname": classname},
            )

            try:
                result = func(*args, **kwargs)
                duration = (time.perf_counter() - start_time) * 1000

                if duration > 1000:
                    logger.warning(
                        f"⚠️ {Colors.YELLOW}SLOW TASK DETECTED{Colors.RESET}: {func.__name__} took {duration / 1000:.2f}s",
                        extra={"classname": classname},
                    )

                logger.debug(
                    f"└─ status: {Colors.GREEN}OK{Colors.RESET} | latency: {duration:.2f}ms",
                    extra={"classname": classname},
                )
                return result
            except Exception as e:
                # Al pasar exc_info=True, guardamos la línea exacta del error en el log
                logger.error(
                    f"└─ {Colors.BOLD}CRASH DETECTED IN WORKER{Colors.RESET} -> Tipo: {type(e).__name__}",
                    exc_info=True,
                    extra={"classname": classname},
                )
                raise e

        return wrapper

    if callable(arg):
        return actual_decorator(arg)
    return lambda f: actual_decorator(f, arg)


# --- INICIO DEL MOTOR ---
logger.info(f"{Colors.CYAN}--- FHVT GALLERY LOGCAT ENGINE READY ---{Colors.RESET}")


def _check_gpu():
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        if "DmlExecutionProvider" in providers:
            logger.info(
                f"{Colors.GREEN}--- HARDWARE IA: GPU DETECTADA (DirectML — AMD/NVIDIA/Intel) ---{Colors.RESET}"
            )
        elif "CUDAExecutionProvider" in providers:
            logger.info(
                f"{Colors.GREEN}--- HARDWARE IA: GPU DETECTADA (CUDA — NVIDIA) ---{Colors.RESET}"
            )
        else:
            logger.warning(
                f"{Colors.YELLOW}--- HARDWARE IA: GPU no disponible via ONNX (Usando CPU) ---{Colors.RESET}"
            )
        logger.info(f"Providers ONNX disponibles: {providers}")
    except ImportError:
        logger.warning(
            f"{Colors.YELLOW}--- HARDWARE IA: onnxruntime no encontrado ---{Colors.RESET}"
        )


threading.Thread(target=_check_gpu, name="HardwareCh", daemon=True).start()
