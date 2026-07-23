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


# Compilar Regex global optimizando CPU
ANSI_REGEX = re.compile(r"\033\[[0-9;]*m")


class LogcatFormatter(logging.Formatter):
    """Imita la estructura: Hora | Thread | Nivel | Tag: Mensaje"""

    def __init__(self, use_colors=True):
        super().__init__()
        self.use_colors = use_colors

    def format(self, record):
        timestamp = self.formatTime(record, "%H:%M:%S")
        thread_name = threading.current_thread().name

        # Extraer Tag contextual dinámico
        if hasattr(record, "classname"):
            tag = f"{record.classname}:{record.funcName}"
        else:
            # Asignar Tag genérico si falta decorador
            tag = f"{os.path.basename(record.pathname)}:{record.funcName}"

        lvl = record.levelname[:1]

        if self.use_colors:
            # Inyectar códigos color ANSI CLI
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
            # Limpiar strings ANSI para output texto plano
            header = f"{timestamp} | {thread_name[:10]:>10} | {lvl} | {tag}: "

        message = record.getMessage()

        # Formatear stack Traceback C++/Python
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                message = f"{message}\n{record.exc_text}"

        # Alinear mensajes multilínea a padding header
        if "\n" in message:
            indent_len = (
                len(ANSI_REGEX.sub("", header)) if self.use_colors else len(header)
            )
            message = message.replace("\n", "\n" + " " * indent_len)

        return f"{header}{message}"


class AntiSpamFilter(logging.Filter):
    """Silencia mensajes idénticos que se repiten masivamente para no congelar la consola."""
    def __init__(self):
        super().__init__()
        self.last_msg = None
        self.repeat_count = 0

    def filter(self, record):
        msg = record.getMessage()
        if msg == self.last_msg:
            self.repeat_count += 1
            if self.repeat_count == 1:
                return True  # Permitimos el primer duplicado por si acaso
            if self.repeat_count % 100 == 0:
                record.msg = f"[Repetido {self.repeat_count} veces] " + record.msg
                return True
            return False
        else:
            self.last_msg = msg
            self.repeat_count = 0
            return True


def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_logger():
    logger = logging.getLogger("FHVT_gallery")
    root_logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Instanciar Handler Console StdOut
        if not getattr(sys, "frozen", False):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(LogcatFormatter(use_colors=True))
            logger.addHandler(console_handler)

        # Instanciar Handler FileAudit plano
        try:
            log_dir = os.path.join(get_base_path(), "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "fhvt_session.log")

            # Abrir modo W purgando historial antiguo
            file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
            file_handler.setFormatter(LogcatFormatter(use_colors=False))
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
            
            # También añadirlo al root logger para capturar warnings de librerías de terceros (ej. huggingface_hub)
            root_logger.addHandler(file_handler)

            # Enganchar FaultHandler capturando SEGFAULT C++
            try:
                import faulthandler

                crash_log = os.path.join(log_dir, "fhvt_crash.log")
                # Preservar file handle GarbageCollector
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
logger.addFilter(AntiSpamFilter())

# Captura de Warnings de Python (Redirige 'warnings.warn' al logger)
logging.captureWarnings(True)
warnings_logger = logging.getLogger("py.warnings")
for handler in logger.handlers:
    warnings_logger.addHandler(handler)

# --- HOOKS GLOBALES DE ERRORES ---
def global_exception_hook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("❌ ERROR FATAL NO CAPTURADO", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = global_exception_hook

def thread_exception_hook(args):
    logger.critical(f"❌ ERROR EN HILO SECUNDARIO '{args.thread.name}'", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

threading.excepthook = thread_exception_hook

def unraisable_exception_hook(args):
    logger.error(f"⚠️ ERROR IGNORE (Unraisable GC): {args.err_msg}", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

sys.unraisablehook = unraisable_exception_hook


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
                # Volcar exc_info logueando stackframe fallido
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
