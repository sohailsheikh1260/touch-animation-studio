"""Skeleton Details screen - shown when clicking a skeleton in Skeleton Master.

Layout: 80% main area (skeleton visualization), 20% sidebar showing skeleton name.
"""

import math

from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QEvent, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import database
import sqlite3
from screens.theme import BG, CARD_BG, MUTED, TEXT


class BoneListWidget(QScrollArea):
    """Scrollable list of bones in the sidebar."""
    
    bone_selected = Signal(str)  # Emits bone_name when clicked
    bone_edit_requested = Signal(int)  # Emits bone_id for editing
    bone_delete_requested = Signal(int)  # Emits bone_id for deletion
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bones: list[sqlite3.Row] = []
        self._selected_bone: str | None = None
        self._item_widgets: dict[str, QFrame] = {}
        
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background-color: transparent; border: none;")
        
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)
        self.layout.addStretch()
        self.setWidget(self.container)
        
    def set_bones(self, bones: list) -> None:
        self._bones = bones
        self._rebuild_list()
        
    def _rebuild_list(self) -> None:
        # Clear existing items
        while self.layout.count() > 1:  # Keep the stretch at the end
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._item_widgets.clear()
        
        # Group bones by hierarchy level for indentation
        bone_map = {b["bone_name"]: b for b in self._bones}
        roots = [b for b in self._bones if b["parent_name"] is None or b["parent_name"] not in bone_map]
        
        for root in roots:
            self._add_bone_item(root["bone_name"], 0, bone_map)
            
    def _add_bone_item(self, bone_name: str, depth: int, bone_map: dict) -> None:
        bone = bone_map.get(bone_name)
        if not bone:
            return
            
        item = QFrame()
        item.setCursor(Qt.PointingHandCursor)
        item.setFixedHeight(28)
        item.setStyleSheet(self._item_style(False))
        item.setContextMenuPolicy(Qt.CustomContextMenu)
        item.customContextMenuRequested.connect(lambda pos, bn=bone_name: self._show_context_menu(pos, bn))
        
        layout = QHBoxLayout(item)
        layout.setContentsMargins(8 + depth * 12, 4, 8, 4)
        layout.setSpacing(8)
        
        # Expand/collapse indicator (placeholder for future)
        indent_label = QLabel("  " * depth)
        layout.addWidget(indent_label)
        
        # Bone icon
        icon = QLabel("●")
        icon.setFixedWidth(16)
        icon.setStyleSheet(f"color: #38bdf8; font-size: 12px;")
        layout.addWidget(icon)
        
        # Bone name
        name_label = QLabel(bone_name.replace("_", " ").title())
        name_label.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        layout.addWidget(name_label)
        
        layout.addStretch()
        
        # Z-order badge
        if bone["z_order"] > 0:
            z_badge = QLabel(f"z{bone['z_order']}")
            z_badge.setStyleSheet(f"color: {MUTED}; font-size: 10px; background-color: #1e293b; border-radius: 3px; padding: 1px 4px;")
            layout.addWidget(z_badge)
        
        def mousePressEvent(event, bn=bone_name):
            if event.button() == Qt.LeftButton:
                self._set_selected(bn)
                self.bone_selected.emit(bn)
        item.mousePressEvent = mousePressEvent
        
        self._item_widgets[bone_name] = item
        self.layout.insertWidget(self.layout.count() - 1, item)  # Insert before stretch
        
        # Recursively add children
        children = [b for b in self._bones if b["parent_name"] == bone_name]
        for child in children:
            self._add_bone_item(child["bone_name"], depth + 1, bone_map)
            
    def _show_context_menu(self, pos, bone_name: str) -> None:
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {CARD_BG}; border: 1px solid #334155; border-radius: 6px; }}"
            f"QMenu::item {{ color: {TEXT}; padding: 8px 24px; }}"
            f"QMenu::item:selected {{ background-color: #334155; }}"
        )
        
        edit_action = menu.addAction("✏️  Edit")
        edit_action.triggered.connect(lambda: self._emit_edit(bone_name))
        
        delete_action = menu.addAction("🗑  Delete")
        delete_action.triggered.connect(lambda: self._emit_delete(bone_name))
        
        menu.exec(self.mapToGlobal(pos))
        
    def _emit_edit(self, bone_name: str) -> None:
        # Find bone id and emit edit signal
        for bone in self._bones:
            if bone["bone_name"] == bone_name:
                self.bone_edit_requested.emit(bone["id"])
                break
        
    def _emit_delete(self, bone_name: str) -> None:
        for bone in self._bones:
            if bone["bone_name"] == bone_name:
                self.bone_delete_requested.emit(bone["id"])
                break
            
    def _item_style(self, selected: bool) -> str:
        if selected:
            return f"QFrame {{ background-color: #0d9488; border-radius: 4px; }}"
        return f"QFrame {{ background-color: transparent; border-radius: 4px; }} QFrame:hover {{ background-color: #334155; }}"
        
    def _set_selected(self, bone_name: str) -> None:
        # Update styles
        for name, widget in self._item_widgets.items():
            widget.setStyleSheet(self._item_style(name == bone_name))
        self._selected_bone = bone_name


class SkeletonCanvas(QWidget):
    """Canvas widget that draws the skeleton hierarchy."""
    
    bone_moved = Signal(str, float, float)  # bone_name, new_x, new_y
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bones: list[sqlite3.Row] = []
        self._bone_map: dict[str, sqlite3.Row] = {}
        self.setMinimumSize(400, 400)
        self.setMouseTracking(True)
        self._hovered_bone: str | None = None
        self._selected_bone: str | None = None
        self._scale = 1.0
        self._offset_x = 0
        self._offset_y = 0
        
        # Dragging state
        self._dragging_bone: str | None = None
        self._drag_start_pos: QPointF | None = None
        self._drag_bone_start_offset: QPointF | None = None
        # Live drag offsets for real-time visual feedback
        self._live_drag_offsets: dict[str, QPointF] = {}
        
    def set_bones(self, bones: list) -> None:
        self._bones = bones
        self._bone_map = {b["bone_name"]: b for b in bones}
        self.update()
        
    def set_skeleton_id(self, skeleton_id: int) -> None:
        """Set skeleton ID for saving bone positions."""
        self._skeleton_id = skeleton_id
        
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Fill background
        painter.fillRect(self.rect(), QColor(BG))
        
        if not self._bones:
            painter.setPen(QColor(MUTED))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(self.rect(), Qt.AlignCenter, "No bones in this skeleton")
            return
            
        # Calculate center
        center_x = self.width() / 2 + self._offset_x
        center_y = self.height() / 2 + self._offset_y
        
        # Build hierarchy and compute positions
        positions = self._compute_positions(center_x, center_y)
        
        # Draw bones (lines first, then joints)
        self._draw_bones(painter, positions)
        self._draw_joints(painter, positions)
        
    def _compute_positions(self, center_x: float, center_y: float) -> dict[str, QPointF]:
        """Compute screen positions for each bone based on hierarchy."""
        positions = {}
        
        # Find root bones (no parent or parent not in map)
        roots = [b for b in self._bones if b["parent_name"] is None or b["parent_name"] not in self._bone_map]
        
        # If no clear root, use first bone
        if not roots:
            roots = [self._bones[0]]
            
        for root in roots:
            self._layout_bone(root["bone_name"], center_x, center_y, 0, positions, set())
            
        return positions
        
    def _layout_bone(self, bone_name: str, x: float, y: float, depth: int, 
                     positions: dict, visited: set) -> None:
        """Recursively layout bones using a tree layout algorithm."""
        if bone_name in visited:
            return
        visited.add(bone_name)
        
        bone = self._bone_map.get(bone_name)
        if not bone:
            return
            
        # Apply live drag offset for this bone if dragging
        if bone_name in self._live_drag_offsets:
            live_offset = self._live_drag_offsets[bone_name]
            x += live_offset.x() * self._scale
            y += live_offset.y() * self._scale
        else:
            x += bone["x_offset"] * self._scale
            y += bone["y_offset"] * self._scale
            
        positions[bone_name] = QPointF(x, y)
        
        # Find children
        children = [b for b in self._bones if b["parent_name"] == bone_name]
        
        if not children:
            return
            
        # Layout children in a fan
        num_children = len(children)
        start_angle = -90  # Start pointing up
        angle_step = 180 / max(1, num_children - 1) if num_children > 1 else 0
        
        for i, child in enumerate(children):
            angle = start_angle + i * angle_step
            # Use bone length for spacing
            length = max(bone["length"], 40) * self._scale
            rad = math.radians(angle)
            child_x = x + length * math.cos(rad)
            child_y = y + length * math.sin(rad)
            
            # Apply child's offset (use live drag offset if dragging this bone)
            if child["bone_name"] in self._live_drag_offsets:
                live_offset = self._live_drag_offsets[child["bone_name"]]
                child_x += live_offset.x() * self._scale
                child_y += live_offset.y() * self._scale
            else:
                child_x += child["x_offset"] * self._scale
                child_y += child["y_offset"] * self._scale
            
            self._layout_bone(child["bone_name"], child_x, child_y, depth + 1, positions, visited)
            
    def _draw_bones(self, painter: QPainter, positions: dict) -> None:
        """Draw bone connections as lines."""
        pen = QPen(QColor("#38bdf8"), 2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        
        for bone in self._bones:
            parent_name = bone["parent_name"]
            if parent_name and parent_name in positions and bone["bone_name"] in positions:
                p1 = positions[parent_name]
                p2 = positions[bone["bone_name"]]
                painter.drawLine(p1, p2)
                
    def _draw_joints(self, painter: QPainter, positions: dict) -> None:
        """Draw bone joints as circles with labels."""
        for bone in self._bones:
            name = bone["bone_name"]
            if name not in positions:
                continue
                
            pos = positions[name]
            is_hovered = name == self._hovered_bone
            is_selected = name == self._selected_bone
            
            # Joint circle
            radius = 10 if (is_hovered or is_selected) else 8
            if is_selected:
                painter.setBrush(QBrush(QColor("#0d9488")))
                painter.setPen(QPen(QColor("#14b8a6"), 3))
            elif is_hovered:
                painter.setBrush(QBrush(QColor("#38bdf8")))
                painter.setPen(QPen(QColor("#0ea5e9"), 2))
            else:
                painter.setBrush(QBrush(QColor("#1e293b")))
                painter.setPen(QPen(QColor("#334155"), 2))
                
            painter.drawEllipse(pos, radius, radius)
            
            # Label
            painter.setPen(QColor(TEXT))
            painter.setFont(QFont("Arial", 8))
            metrics = QFontMetrics(painter.font())
            text = name.replace("_", " ").title()
            text_rect = metrics.boundingRect(text)
            text_x = pos.x() - text_rect.width() / 2
            text_y = pos.y() - radius - 4
            painter.drawText(int(text_x), int(text_y), text)
            
            # Z-order indicator (small number)
            if bone["z_order"] > 0:
                painter.setPen(QColor(MUTED))
                painter.setFont(QFont("Arial", 7))
                painter.drawText(int(pos.x() - 4), int(pos.y() + radius + 12), f"z:{bone['z_order']}")
                
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        if not self._bones:
            return
            
        center_x = self.width() / 2 + self._offset_x
        center_y = self.height() / 2 + self._offset_y
        positions = self._compute_positions(center_x, center_y)
        
        for bone in self._bones:
            name = bone["bone_name"]
            if name in positions:
                pos = positions[name]
                dx = event.position().x() - pos.x()
                dy = event.position().y() - pos.y()
                if dx * dx + dy * dy < 100:  # 10px radius
                    self._dragging_bone = name
                    self._drag_start_pos = event.position()
                    self._drag_bone_start_offset = QPointF(bone["x_offset"], bone["y_offset"])
                    self.setCursor(Qt.ClosedHandCursor)
                    break
                    
    def mouseMoveEvent(self, event) -> None:
        if self._dragging_bone:
            # Update bone position while dragging (real-time)
            if self._drag_start_pos is not None:
                delta = event.position() - self._drag_start_pos
                # Convert screen delta to bone offset (accounting for scale)
                new_x = self._drag_bone_start_offset.x() + delta.x() / self._scale
                new_y = self._drag_bone_start_offset.y() + delta.y() / self._scale
                
                # Store live offset for real-time rendering
                self._live_drag_offsets[self._dragging_bone] = QPointF(new_x, new_y)
                
            self.update()
            return
            
        # Check hover over joints (when not dragging)
        if not self._bones:
            return
            
        center_x = self.width() / 2 + self._offset_x
        center_y = self.height() / 2 + self._offset_y
        positions = self._compute_positions(center_x, center_y)
        
        hovered = None
        for bone in self._bones:
            name = bone["bone_name"]
            if name in positions:
                pos = positions[name]
                dx = event.position().x() - pos.x()
                dy = event.position().y() - pos.y()
                if dx * dx + dy * dy < 100:  # 10px radius
                    hovered = name
                    break
                    
        if hovered != self._hovered_bone:
            self._hovered_bone = hovered
            self.update()
            
    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        if self._dragging_bone and self._drag_start_pos is not None:
            # Get final live offset
            final_offset = self._live_drag_offsets.get(self._dragging_bone)
            if final_offset:
                bone = self._bone_map.get(self._dragging_bone)
                if bone:
                    new_x = final_offset.x()
                    new_y = final_offset.y()
                    
                    # Save to database
                    import database
                    database.update_skeleton_bone(
                        bone["id"],
                        bone["bone_name"],
                        bone["parent_name"],
                        new_x, new_y,
                        bone["length"],
                        bone["angle"],
                        bone["z_order"]
                    )
                    
                    # Emit signal to refresh
                    self.bone_moved.emit(self._dragging_bone, new_x, new_y)
            
            # Clear live drag offset
            self._live_drag_offsets.pop(self._dragging_bone, None)
                
        self._dragging_bone = None
        self._drag_start_pos = None
        self._drag_bone_start_offset = None
        self.setCursor(Qt.ArrowCursor)
        self.update()
            
    def leaveEvent(self, event) -> None:
        self._hovered_bone = None
        # If dragging and mouse leaves widget, cancel drag
        if self._dragging_bone:
            self._live_drag_offsets.pop(self._dragging_bone, None)
            self._dragging_bone = None
            self._drag_start_pos = None
            self._drag_bone_start_offset = None
            self.setCursor(Qt.ArrowCursor)
        self.update()
        
    def wheelEvent(self, event) -> None:
        # Zoom
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        self._scale *= factor
        self._scale = max(0.3, min(self._scale, 3.0))
        self.update()


class SkeletonDetailsPage(QWidget):
    DRAWER_WIDTH = 280
    
    def __init__(
        self,
        go_back,
        set_status,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._go_back = go_back
        self._set_status = set_status
        self._skeleton_id: int | None = None
        self._bones: list = []

        # Root layout - horizontal split: sidebar (20%) + main (80%)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar (20%) ----
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; border-right: 1px solid #334155; }}"
        )
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        # Back button
        back_btn = QPushButton("← Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 8px;"
            "  padding: 8px 16px; font-size: 13px; }"
            "QPushButton:hover { background-color: #334155; }"
        )
        back_btn.clicked.connect(self._go_back)
        sidebar_layout.addWidget(back_btn)

        # Skeleton name
        self.sidebar_name = QLabel("Skeleton Name")
        self.sidebar_name.setWordWrap(True)
        self.sidebar_name.setStyleSheet(
            f"color: {TEXT}; font-size: 16px; font-weight: bold;"
        )
        sidebar_layout.addWidget(self.sidebar_name)

        # Bone count
        self.sidebar_bone_count = QLabel("0 bones")
        self.sidebar_bone_count.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        sidebar_layout.addWidget(self.sidebar_bone_count)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #334155;")
        sidebar_layout.addWidget(sep)

        # Bones list label + Add button
        bones_header = QHBoxLayout()
        bones_label = QLabel("BONES")
        bones_label.setStyleSheet(f"color: {MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        bones_header.addWidget(bones_label)
        bones_header.addStretch()
        
        add_bone_btn = QPushButton("＋")
        add_bone_btn.setFixedSize(24, 24)
        add_bone_btn.setToolTip("Add Bone")
        add_bone_btn.setCursor(Qt.PointingHandCursor)
        add_bone_btn.setStyleSheet(
            f"QPushButton {{ background-color: #0d9488; color: {TEXT};"
            "  border: none; border-radius: 12px; font-size: 16px; font-weight: bold; }}"
            "QPushButton:hover { background-color: #14b8a6; }"
        )
        add_bone_btn.clicked.connect(lambda: self.open_bone_drawer())
        bones_header.addWidget(add_bone_btn)
        sidebar_layout.addLayout(bones_header)

        # Bone list widget
        self.bone_list = BoneListWidget()
        self.bone_list.bone_selected.connect(self._on_bone_selected)
        self.bone_list.bone_edit_requested.connect(self.open_bone_drawer)
        self.bone_list.bone_delete_requested.connect(self._on_bone_delete_from_list)
        sidebar_layout.addWidget(self.bone_list, 1)

        root.addWidget(self.sidebar, 1)

        # ---- Main area (80%) ----
        self.main_area = QFrame()
        self.main_area.setStyleSheet(f"background-color: {BG};")
        main_layout = QVBoxLayout(self.main_area)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Title bar
        title_bar = QHBoxLayout()
        self.main_title = QLabel("Skeleton Details")
        self.main_title.setStyleSheet(f"color: {TEXT}; font-size: 20px; font-weight: bold;")
        title_bar.addWidget(self.main_title)
        title_bar.addStretch()
        
        # Zoom controls
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedSize(32, 32)
        zoom_out_btn.setToolTip("Zoom out")
        zoom_out_btn.clicked.connect(lambda: self._zoom(0.9))
        zoom_out_btn.setStyleSheet(self._button_style())
        
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(32, 32)
        zoom_in_btn.setToolTip("Zoom in")
        zoom_in_btn.clicked.connect(lambda: self._zoom(1.1))
        zoom_in_btn.setStyleSheet(self._button_style())
        
        reset_btn = QPushButton("⌂")
        reset_btn.setFixedSize(32, 32)
        reset_btn.setToolTip("Reset view")
        reset_btn.clicked.connect(self._reset_view)
        reset_btn.setStyleSheet(self._button_style())
        
        title_bar.addWidget(zoom_out_btn)
        title_bar.addWidget(zoom_in_btn)
        title_bar.addWidget(reset_btn)
        main_layout.addLayout(title_bar)

        # Canvas in scroll area for large skeletons
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(f"background-color: {BG}; border: none;")
        
        self.canvas = SkeletonCanvas()
        self.canvas.bone_moved.connect(self._on_bone_moved)
        self.scroll.setWidget(self.canvas)
        main_layout.addWidget(self.scroll, 1)

        root.addWidget(self.main_area, 4)

    def _button_style(self) -> str:
        return (
            f"QPushButton {{ background-color: {CARD_BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 6px; font-size: 14px; }"
            "QPushButton:hover { background-color: #334155; }"
        )

    def _zoom(self, factor: float) -> None:
        self.canvas._scale *= factor
        self.canvas._scale = max(0.3, min(self.canvas._scale, 3.0))
        self.canvas.update()

    def _reset_view(self) -> None:
        self.canvas._scale = 1.0
        self.canvas._offset_x = 0
        self.canvas._offset_y = 0
        self.canvas.update()

    def _on_bone_selected(self, bone_name: str) -> None:
        """Handle bone selection from sidebar list."""
        self.canvas._selected_bone = bone_name
        self.canvas.update()
        if self._set_status:
            self._set_status(f"Selected bone: {bone_name.replace('_', ' ').title()}")

    def _on_bone_moved(self, bone_name: str, new_x: float, new_y: float) -> None:
        """Handle bone position change from canvas drag."""
        self._refresh_bones()
        if self._set_status:
            self._set_status(f"Moved {bone_name.replace('_', ' ').title()} to ({new_x:.1f}, {new_y:.1f})")

    def show_skeleton(self, skeleton) -> None:
        """Display the given skeleton row."""
        self._skeleton_id = skeleton["id"]
        self.sidebar_name.setText(skeleton["name"])
        self.main_title.setText(f"🦴  {skeleton['name']}")
        
        # Load bones
        bones = database.list_skeleton_master_bones(skeleton["id"])
        self._bones = bones  # Store for dropdown
        self.canvas.set_bones(bones)
        self.canvas.set_skeleton_id(skeleton["id"])
        self.bone_list.set_bones(bones)
        self.sidebar_bone_count.setText(f"{len(bones)} bones")
        
        if self._set_status:
            self._set_status(f"Viewing skeleton: {skeleton['name']} ({len(bones)} bones)")

    def resizeEvent(self, event) -> None:
        """Adjust sidebar width to ~20% of window width."""
        super().resizeEvent(event)
        sidebar_width = int(self.width() * 0.2)
        sidebar_width = max(180, min(sidebar_width, 280))
        self.sidebar.setFixedWidth(sidebar_width)

    # -------------------------------------------------------- Bone Drawer
    def _build_bone_drawer(self) -> None:
        """Build the slide-in drawer for creating/editing bones."""
        
        self.bone_overlay = QWidget(self)
        self.bone_overlay.setStyleSheet("background-color: rgba(2, 6, 23, 160);")
        self.bone_overlay.hide()
        self.bone_overlay.installEventFilter(self)

        self.bone_drawer = QFrame(self)
        self.bone_drawer.setFixedWidth(self.DRAWER_WIDTH)
        self.bone_drawer.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; border-left: 2px solid #0d9488; }}"
        )
        
        layout = QVBoxLayout(self.bone_drawer)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        self.bone_drawer_title = QLabel("Add Bone")
        self.bone_drawer_title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: bold;")
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 6px; font-size: 12px; }}"
            "QPushButton:hover { background-color: #334155; }"
        )
        close_btn.clicked.connect(self.close_bone_drawer)
        header.addWidget(self.bone_drawer_title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        # Bone name
        name_hint = QLabel("Bone name")
        name_hint.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self.bone_name_input = QLineEdit()
        self.bone_name_input.setPlaceholderText("e.g. hand_left_lower")
        self.bone_name_input.setStyleSheet(
            f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 6px;"
            "  padding: 6px 10px; font-size: 13px; }}"
        )
        self.bone_name_input.returnPressed.connect(self._on_bone_save)
        layout.addWidget(name_hint)
        layout.addWidget(self.bone_name_input)

        # Parent bone dropdown
        parent_hint = QLabel("Parent bone")
        parent_hint.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self.bone_parent_combo = QComboBox()
        self.bone_parent_combo.setStyleSheet(
            f"QComboBox {{ background-color: {BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 6px;"
            "  padding: 6px 10px; font-size: 13px; }}"
            "QComboBox::drop-down { border: none; }"
        )
        self.bone_parent_combo.addItem("(Root - no parent)", None)
        layout.addWidget(parent_hint)
        layout.addWidget(self.bone_parent_combo)

        # Position/Length inputs
        grid = QGridLayout()
        grid.setSpacing(8)
        
        # X offset
        grid.addWidget(QLabel("X offset"), 0, 0)
        self.bone_x_input = QLineEdit()
        self.bone_x_input.setPlaceholderText("0")
        self.bone_x_input.setStyleSheet(self.bone_name_input.styleSheet())
        grid.addWidget(self.bone_x_input, 0, 1)
        
        # Y offset
        grid.addWidget(QLabel("Y offset"), 1, 0)
        self.bone_y_input = QLineEdit()
        self.bone_y_input.setPlaceholderText("0")
        self.bone_y_input.setStyleSheet(self.bone_name_input.styleSheet())
        grid.addWidget(self.bone_y_input, 1, 1)
        
        # Length
        grid.addWidget(QLabel("Length"), 2, 0)
        self.bone_length_input = QLineEdit()
        self.bone_length_input.setPlaceholderText("50")
        self.bone_length_input.setStyleSheet(self.bone_name_input.styleSheet())
        grid.addWidget(self.bone_length_input, 2, 1)
        
        # Angle
        grid.addWidget(QLabel("Angle (°)"), 3, 0)
        self.bone_angle_input = QLineEdit()
        self.bone_angle_input.setPlaceholderText("0")
        self.bone_angle_input.setStyleSheet(self.bone_name_input.styleSheet())
        grid.addWidget(self.bone_angle_input, 3, 1)
        
        # Z-order
        grid.addWidget(QLabel("Z-order"), 4, 0)
        self.bone_z_input = QLineEdit()
        self.bone_z_input.setPlaceholderText("0")
        self.bone_z_input.setStyleSheet(self.bone_name_input.styleSheet())
        grid.addWidget(self.bone_z_input, 4, 1)
        
        layout.addLayout(grid)

        layout.addStretch()

        # Delete button
        self.bone_delete_btn = QPushButton("🗑  Delete")
        self.bone_delete_btn.setCursor(Qt.PointingHandCursor)
        self.bone_delete_btn.setStyleSheet(
            f"QPushButton {{ background-color: #7f1d1d; color: {TEXT};"
            "  border: none; border-radius: 6px; padding: 8px; font-size: 12px; }}"
            "QPushButton:hover { background-color: #991b1b; }"
        )
        self.bone_delete_btn.clicked.connect(self._on_bone_delete)
        layout.addWidget(self.bone_delete_btn)

        # Save button
        self.bone_save_btn = QPushButton("💾  Save Bone")
        self.bone_save_btn.setCursor(Qt.PointingHandCursor)
        self.bone_save_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: #e2e8f0;"
            "  border: none; border-radius: 6px; padding: 8px;"
            "  font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #22c55e; }"
        )
        self.bone_save_btn.clicked.connect(self._on_bone_save)
        layout.addWidget(self.bone_save_btn)

        # Animation
        self._bone_anim = QPropertyAnimation(self.bone_drawer, b"pos", self)
        self._bone_anim.setDuration(220)
        self._bone_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._bone_anim.finished.connect(self._after_bone_anim)

    def open_bone_drawer(self, bone_id: int | None = None) -> None:
        """Open drawer for adding/editing a bone."""
        if self._skeleton_id is None:
            QMessageBox.warning(self, "No skeleton", "Please select a skeleton first.")
            return
        self._editing_bone_id = bone_id
        
        # Build drawer if not built yet
        if not hasattr(self, 'bone_drawer'):
            self._build_bone_drawer()
        
        # Populate parent combo with current bones
        self.bone_parent_combo.clear()
        self.bone_parent_combo.addItem("", None)  # Empty = root bone
        for bone in self._bones:
            self.bone_parent_combo.addItem(bone["bone_name"].replace("_", " ").title(), bone["bone_name"])
        
        if bone_id is None:
            self.bone_drawer_title.setText("Add Bone")
            self.bone_name_input.clear()
            self.bone_parent_combo.setCurrentIndex(0)
            self.bone_x_input.clear()
            self.bone_y_input.clear()
            self.bone_length_input.setText("50")
            self.bone_angle_input.setText("0")
            self.bone_z_input.setText("0")
            self.bone_delete_btn.hide()
        else:
            # Find bone by id
            bone = None
            for b in self._bones:
                if b["id"] == bone_id:
                    bone = b
                    break
            if bone is None:
                return
            self.bone_drawer_title.setText("Edit Bone")
            self.bone_name_input.setText(bone["bone_name"])
            # Set parent
            idx = self.bone_parent_combo.findData(bone["parent_name"])
            if idx >= 0:
                self.bone_parent_combo.setCurrentIndex(idx)
            self.bone_x_input.setText(str(bone["x_offset"]))
            self.bone_y_input.setText(str(bone["y_offset"]))
            self.bone_length_input.setText(str(bone["length"]))
            self.bone_angle_input.setText(str(bone["angle"]))
            self.bone_z_input.setText(str(bone["z_order"]))
            self.bone_delete_btn.show()

        self.bone_name_input.setFocus()

        # Slide in from right
        h = self.height()
        self.bone_overlay.setGeometry(0, 0, self.width(), h)
        self.bone_overlay.show()
        self.bone_overlay.raise_()
        self.bone_drawer.setGeometry(self.width(), 0, self.DRAWER_WIDTH, h)
        self.bone_drawer.show()
        self.bone_drawer.raise_()
        self._bone_anim.stop()
        self._bone_anim.setStartValue(QPoint(self.width(), 0))
        self._bone_anim.setEndValue(QPoint(self.width() - self.DRAWER_WIDTH, 0))
        self._bone_anim.start()

    def close_bone_drawer(self) -> None:
        if not hasattr(self, '_bone_anim'):
            return
        self._bone_anim.stop()
        self._bone_anim.setStartValue(self.bone_drawer.pos())
        self._bone_anim.setEndValue(QPoint(self.width(), 0))
        self._bone_anim.start()

    def _after_bone_anim(self) -> None:
        if self._bone_anim.endValue().x() >= self.width():
            self.bone_drawer.hide()
            self.bone_overlay.hide()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is getattr(self, 'bone_overlay', None) and event.type() == QEvent.MouseButtonPress:
            self.close_bone_drawer()
            return True
        return super().eventFilter(obj, event)

    def _on_bone_save(self) -> None:
        name = self.bone_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter the bone name.")
            return
        
        try:
            parent_name = self.bone_parent_combo.currentData()
            x_offset = float(self.bone_x_input.text() or 0)
            y_offset = float(self.bone_y_input.text() or 0)
            length = float(self.bone_length_input.text() or 50)
            angle = float(self.bone_angle_input.text() or 0)
            z_order = int(self.bone_z_input.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Please enter valid numbers for position/length/angle/z-order.")
            return

        try:
            if self._editing_bone_id is None:
                database.create_skeleton_master_bone(
                    self._skeleton_id, name, parent_name,
                    x_offset, y_offset, length, angle, z_order
                )
                message = f"Created bone '{name}'."
            else:
                database.update_skeleton_bone(
                    self._editing_bone_id, name, parent_name,
                    x_offset, y_offset, length, angle, z_order
                )
                message = f"Saved bone '{name}'."
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot save bone", str(exc))
            return

        # Refresh
        self._refresh_bones()
        self.close_bone_drawer()
        if self._set_status:
            self._set_status(message)

    def _on_bone_delete(self) -> None:
        if self._editing_bone_id is None:
            return
        bone = database.get_skeleton_bone(self._editing_bone_id)
        if bone is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete bone",
            f"Delete bone '{bone['bone_name']}'?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_skeleton_bone(bone["id"])
        self._refresh_bones()
        self.close_bone_drawer()
        if self._set_status:
            self._set_status(f"Deleted bone '{bone['bone_name']}'.")

    def _on_bone_delete_from_list(self, bone_id: int) -> None:
        """Delete bone from context menu in bone list."""
        bone = database.get_skeleton_bone(bone_id)
        if bone is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete bone",
            f"Delete bone '{bone['bone_name']}'?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_skeleton_bone(bone["id"])
        self._refresh_bones()
        if self._set_status:
            self._set_status(f"Deleted bone '{bone['bone_name']}'.")

    def _refresh_bones(self) -> None:
        """Reload bones from database and update UI."""
        bones = database.list_skeleton_master_bones(self._skeleton_id)
        self.canvas.set_bones(bones)
        self.bone_list.set_bones(bones)
        self.sidebar_bone_count.setText(f"{len(bones)} bones")