"""PDF report export dialog."""

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)


class PdfReportDialog(QDialog):
    """Dialog for configuring the multi-page PDF report.

    Allows the user to choose paper size, orientation, which pages to include,
    and report metadata (project name, author).
    """

    def __init__(
        self,
        project_name: str = "Garden Plan",
        author: str = "",
        parent: object = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export PDF Report"))
        self.setModal(True)
        self.setMinimumWidth(440)

        self._project_name_edit: QLineEdit
        self._author_edit: QLineEdit
        self._size_group: QButtonGroup
        self._orientation_group: QButtonGroup
        self._cb_cover: QCheckBox
        self._cb_overview: QCheckBox
        self._cb_bed_details: QCheckBox
        self._cb_plant_list: QCheckBox
        self._cb_legend: QCheckBox

        self._setup_ui(project_name, author)

    def _setup_ui(self, project_name: str, author: str) -> None:
        layout = QVBoxLayout(self)

        # --- Metadata group ---
        meta_group = QGroupBox(self.tr("Report Information"))
        meta_form = QFormLayout(meta_group)

        self._project_name_edit = QLineEdit(project_name)
        meta_form.addRow(self.tr("Project name:"), self._project_name_edit)

        self._author_edit = QLineEdit(author)
        meta_form.addRow(self.tr("Author:"), self._author_edit)

        layout.addWidget(meta_group)

        # --- Paper size & orientation ---
        paper_group = QGroupBox(self.tr("Paper"))
        paper_layout = QHBoxLayout(paper_group)

        size_box = QGroupBox(self.tr("Size"))
        size_vbox = QVBoxLayout(size_box)
        self._size_group = QButtonGroup(self)
        for i, name in enumerate(["A4", "A3", "Letter", "Legal"]):
            rb = QRadioButton(name)
            if i == 0:
                rb.setChecked(True)
            self._size_group.addButton(rb, i)
            size_vbox.addWidget(rb)
        paper_layout.addWidget(size_box)

        orient_box = QGroupBox(self.tr("Orientation"))
        orient_vbox = QVBoxLayout(orient_box)
        self._orientation_group = QButtonGroup(self)
        landscape_rb = QRadioButton(self.tr("Landscape"))
        landscape_rb.setChecked(True)
        portrait_rb = QRadioButton(self.tr("Portrait"))
        self._orientation_group.addButton(landscape_rb, 0)
        self._orientation_group.addButton(portrait_rb, 1)
        orient_vbox.addWidget(landscape_rb)
        orient_vbox.addWidget(portrait_rb)
        paper_layout.addWidget(orient_box)

        layout.addWidget(paper_group)

        # --- Pages to include ---
        pages_group = QGroupBox(self.tr("Pages to Include"))
        pages_vbox = QVBoxLayout(pages_group)

        self._cb_cover = QCheckBox(self.tr("Cover page"))
        self._cb_cover.setChecked(True)
        self._cb_overview = QCheckBox(self.tr("Plan overview (full garden)"))
        self._cb_overview.setChecked(True)
        self._cb_bed_details = QCheckBox(self.tr("Bed detail views (one page per bed)"))
        self._cb_bed_details.setChecked(False)
        self._cb_plant_list = QCheckBox(self.tr("Plant list"))
        self._cb_plant_list.setChecked(True)
        self._cb_legend = QCheckBox(self.tr("Legend (layers)"))
        self._cb_legend.setChecked(True)

        for cb in (
            self._cb_cover,
            self._cb_overview,
            self._cb_bed_details,
            self._cb_plant_list,
            self._cb_legend,
        ):
            pages_vbox.addWidget(cb)

        layout.addWidget(pages_group)

        # Info label
        info = QLabel(
            self.tr("A progress dialog will appear during export.")
        )
        info.setProperty("secondary", True)
        layout.addWidget(info)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    # --- Properties ---

    @property
    def project_name(self) -> str:
        return self._project_name_edit.text().strip() or "Garden Plan"

    @property
    def author(self) -> str:
        return self._author_edit.text().strip()

    @property
    def paper_size(self) -> str:
        names = ["A4", "A3", "Letter", "Legal"]
        idx = self._size_group.checkedId()
        return names[idx] if 0 <= idx < len(names) else "A4"

    @property
    def orientation(self) -> str:
        return "portrait" if self._orientation_group.checkedId() == 1 else "landscape"

    @property
    def include_cover(self) -> bool:
        return self._cb_cover.isChecked()

    @property
    def include_overview(self) -> bool:
        return self._cb_overview.isChecked()

    @property
    def include_bed_details(self) -> bool:
        return self._cb_bed_details.isChecked()

    @property
    def include_plant_list(self) -> bool:
        return self._cb_plant_list.isChecked()

    @property
    def include_legend(self) -> bool:
        return self._cb_legend.isChecked()
