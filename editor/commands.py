from PyQt6.QtGui import QUndoCommand

class EditorCommand(QUndoCommand):
    """Encapsula un cambio de estado para el sistema Undo/Redo de Qt."""
    PARAM_KEYS = ['brightness', 'contrast', 'angle', 'flip_h', 'flip_v', 
                  'canvas_L', 'canvas_T', 'canvas_R', 'canvas_B', 'canvas_bg_color']

    def __init__(self, editor, description, is_destructive=False):
        super().__init__(description)
        self.editor = editor
        self.is_destructive = is_destructive
        
        self.old_params = self._get_current_params()
        if is_destructive:
            self.old_pixmap = self.editor.original_pixmap.copy()
            
        self.new_params = None
        self.new_pixmap = None

    def _get_current_params(self):
        return {k: getattr(self.editor, k) for k in self.PARAM_KEYS}

    def capture_new_state(self):
        self.new_params = self._get_current_params()
        if self.is_destructive:
            self.new_pixmap = self.editor.original_pixmap.copy()

    def redo(self):
        if self.new_params:
            self._apply_state(self.new_params, self.new_pixmap)

    def undo(self):
        self._apply_state(self.old_params, self.old_pixmap if self.is_destructive else None)

    def _apply_state(self, params, pixmap=None):
        for k, v in params.items():
            setattr(self.editor, k, v)
        if pixmap:
            self.editor.original_pixmap = pixmap
        self.editor.update_image()
        self.editor._sync_ui_to_state()
