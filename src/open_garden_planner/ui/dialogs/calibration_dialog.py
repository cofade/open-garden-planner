"""Dialog for two-point image calibration."""

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class CalibrationDialog(QDialog):
    """Dialog for calibrating background image scale using two points.

    User clicks two points on the image and enters the real-world distance
    between them.
    """

    def __init__(self, image_pixmap: QPixmap, parent=None) -> None:
        """Initialize the calibration dialog.

        Args:
            image_pixmap: The background image to calibrate
            parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle("Calibrate Background Image")
        self.setModal(True)
        self.setMinimumSize(600, 500)

        self._original_pixmap = image_pixmap
        self._points: list[QPointF] = []
        self._pixel_distance = 0.0

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "<b>Instructions:</b><br>"
            "1. Click two points on the image at a known distance apart<br>"
            "2. Enter the real-world distance between those points<br>"
            "3. Click OK to apply calibration"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Image view for clicking points
        self._scene = QGraphicsScene()
        self._view = CalibrationImageView(self._scene)
        self._view.point_clicked.connect(self._on_point_clicked)
        self._view.setMinimumHeight(300)

        # Add the image to the scene
        self._pixmap_item = self._scene.addPixmap(self._original_pixmap)
        self._pixmap_item.setPos(0, 0)

        # Fit the image in view
        self._view.fitInView(
            self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio
        )

        layout.addWidget(self._view)

        # Status label
        self._status_label = QLabel("Click the first point on the image")
        self._status_label.setStyleSheet("color: #0066cc; font-weight: bold;")
        layout.addWidget(self._status_label)

        # Distance input
        distance_layout = QHBoxLayout()
        distance_layout.addWidget(QLabel("Real-world distance:"))

        self._distance_input = QLineEdit()
        self._distance_input.setPlaceholderText("e.g., 1200 (cm) or 12 (m)")
        self._distance_input.setEnabled(False)
        distance_layout.addWidget(self._distance_input)

        self._unit_label = QLabel("cm")
        distance_layout.addWidget(self._unit_label)

        self._reset_button = QPushButton("Reset Points")
        self._reset_button.clicked.connect(self._reset_points)
        self._reset_button.setEnabled(False)
        distance_layout.addWidget(self._reset_button)

        layout.addLayout(distance_layout)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self._ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setEnabled(False)
        layout.addWidget(button_box)

    def _on_point_clicked(self, point: QPointF) -> None:
        """Handle point click on the image.

        Args:
            point: The clicked point in scene coordinates
        """
        if len(self._points) < 2:
            self._points.append(point)
            self._draw_calibration_markers()

            if len(self._points) == 1:
                self._status_label.setText("Click the second point on the image")
                self._reset_button.setEnabled(True)
            elif len(self._points) == 2:
                # Calculate pixel distance
                line = QLineF(self._points[0], self._points[1])
                self._pixel_distance = line.length()

                self._status_label.setText(
                    f"Distance: {self._pixel_distance:.1f} pixels. "
                    "Enter the real-world distance below."
                )
                self._distance_input.setEnabled(True)
                self._distance_input.setFocus()
                self._ok_button.setEnabled(True)

    def _draw_calibration_markers(self) -> None:
        """Draw markers and line for calibration points."""
        # Clear previous markers (keep the pixmap)
        for item in self._scene.items():
            if item != self._pixmap_item:
                self._scene.removeItem(item)

        # Draw markers for each point
        pen = QPen(Qt.GlobalColor.red, 3)
        for i, point in enumerate(self._points):
            # Draw a crosshair
            size = 10
            self._scene.addLine(
                point.x() - size, point.y(), point.x() + size, point.y(), pen
            )
            self._scene.addLine(
                point.x(), point.y() - size, point.x(), point.y() + size, pen
            )

            # Draw point number
            text = self._scene.addText(str(i + 1))
            text.setPos(point.x() + 15, point.y() - 15)
            text.setDefaultTextColor(Qt.GlobalColor.red)

        # Draw line between points if we have two
        if len(self._points) == 2:
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            self._scene.addLine(
                QLineF(self._points[0], self._points[1]), pen
            )

    def _reset_points(self) -> None:
        """Reset the calibration points."""
        self._points.clear()
        self._pixel_distance = 0.0

        # Clear markers
        for item in self._scene.items():
            if item != self._pixmap_item:
                self._scene.removeItem(item)

        self._status_label.setText("Click the first point on the image")
        self._distance_input.clear()
        self._distance_input.setEnabled(False)
        self._ok_button.setEnabled(False)
        self._reset_button.setEnabled(False)

    def get_calibration_data(self) -> tuple[float, float] | None:
        """Get the calibration data (pixel distance, real-world cm).

        Returns:
            Tuple of (pixel_distance, centimeters) or None if invalid
        """
        if len(self._points) != 2:
            return None

        # Parse distance input
        try:
            distance_text = self._distance_input.text().strip()
            distance = float(distance_text)
            if distance <= 0:
                return None
            # Distance is already in cm
            return (self._pixel_distance, distance)
        except ValueError:
            return None


class CalibrationImageView(QGraphicsView):
    """Graphics view for clicking calibration points on an image."""

    # Signal definition at class level
    from PyQt6.QtCore import pyqtSignal

    point_clicked = pyqtSignal(QPointF)

    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        """Initialize the view.

        Args:
            scene: The graphics scene
            parent: Parent widget
        """
        super().__init__(scene, parent)

        # Set up view properties
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to capture calibration points.

        Args:
            event: The mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Convert view coordinates to scene coordinates
            scene_pos = self.mapToScene(event.pos())
            self.point_clicked.emit(scene_pos)
        else:
            super().mousePressEvent(event)
