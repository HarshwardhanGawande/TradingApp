"""
Zerodha Trading Dashboard - PyQt6 GUI (Compact UI)
"""

import sys
import os
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QLabel, QPushButton,
    QComboBox, QSpinBox, QDoubleSpinBox, QGroupBox, QFormLayout,
    QMessageBox, QHeaderView, QGridLayout, QTextEdit, QCheckBox,
    QFrame, QDialog, QRadioButton
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from trading_client_cd import ZerodhaClient


# ========== Worker Thread ==========
class ApiWorker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func   = func
        self.args   = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.deleteLater()


# ========== Base Tab ==========
class BaseTab(QWidget):
    def __init__(self, log_callback):
        super().__init__()
        self.log     = log_callback
        self.workers = []
        self.setContentsMargins(2, 2, 2, 2)

    def _run_worker(self, func, finished_callback, error_callback, *args, **kwargs):
        worker = ApiWorker(func, *args, **kwargs)
        worker.finished.connect(finished_callback)
        worker.error.connect(error_callback)
        worker.finished.connect(self._cleanup_workers)
        worker.error.connect(self._cleanup_workers)
        self.workers.append(worker)
        worker.start()

    def _cleanup_workers(self, *args):
        self.workers = [w for w in self.workers if w.isRunning()]


# ========== Holdings Tab ==========
class HoldingsTab(BaseTab):
    def __init__(self, client, log_callback):
        super().__init__(log_callback)
        self.client = client
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(8)

        self.total_invested_label = QLabel("Total Invested: --")
        self.current_value_label  = QLabel("Current Value: --")
        self.day_pnl_label        = QLabel("Day's P&L: --")
        self.total_pnl_label      = QLabel("Total P&L: --")

        compact_style = (
            "font-weight: bold; font-size: 12px; padding: 4px 8px; "
            "background-color: #111318; border-radius: 4px; color: #e0e0e0;"
        )
        for label in [self.total_invested_label, self.current_value_label,
                      self.day_pnl_label, self.total_pnl_label]:
            label.setStyleSheet(compact_style)
            summary_layout.addWidget(label)
        layout.addLayout(summary_layout)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setDefaultSectionSize(24)  # compact rows
        layout.addWidget(self.table)

        btn_refresh = QPushButton("Refresh Holdings")
        btn_refresh.setObjectName("neutralBtn")
        btn_refresh.clicked.connect(self.refresh_data)
        layout.addWidget(btn_refresh)
        self.setLayout(layout)

    def refresh_data(self):
        self.log("Fetching holdings...", category="Info")
        self._run_worker(
            self.client.get_holdings_df,
            self.update_table,
            lambda err: self.log(f"Error: {err}", category="Error", error=True)
        )

    def update_table(self, df: pd.DataFrame):
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            for lbl in [self.total_invested_label, self.current_value_label,
                        self.day_pnl_label, self.total_pnl_label]:
                lbl.setText(lbl.text().split(":")[0] + ": --")
            self.log("No holdings found.", category="Info")
            return

        self.table.setRowCount(df.shape[0])
        self.table.setColumnCount(df.shape[1])
        self.table.setHorizontalHeaderLabels(df.columns)

        for i, row in df.iterrows():
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if j != 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if j in (7, 8):   # Net chg. / Day chg.
                    try:
                        num = float(str(val).replace('%', '').replace('+', ''))
                        if num > 0:
                            item.setForeground(QColor("#00aa55"))
                        elif num < 0:
                            item.setForeground(Qt.GlobalColor.red)
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                    except Exception:
                        pass
                self.table.setItem(i, j, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)

        try:
            holdings       = self.client.get_holdings()
            total_invested = sum(h['average_price'] * h['quantity'] for h in holdings)
            total_current  = sum(h['last_price']    * h['quantity'] for h in holdings)
            day_pnl, total_pnl = self.client.get_holdings_summary()

            self.total_invested_label.setText(f"Total Invested: ₹{total_invested:,.2f}")
            self.total_invested_label.setStyleSheet(
                "font-weight: bold; font-size: 12px; padding: 4px 8px; "
                "background-color: #111318; border-radius: 4px; color: #e0e0e0;")

            if total_current > total_invested:
                self.current_value_label.setText(f"Current Value: ₹{total_current:,.2f} ▲")
                self.current_value_label.setStyleSheet(
                    "font-weight: bold; font-size: 12px; padding: 4px 8px; "
                    "background-color: #111318; border-radius: 4px; color: #00aa55;")
            else:
                self.current_value_label.setText(f"Current Value: ₹{total_current:,.2f}")
                self.current_value_label.setStyleSheet(
                    "font-weight: bold; font-size: 12px; padding: 4px 8px; "
                    "background-color: #111318; border-radius: 4px; color: #e0e0e0;")

            day_pct  = (day_pnl / total_invested * 100) if total_invested else 0
            self.day_pnl_label.setText(
                f"Day's P&L: ₹{day_pnl:,.2f} ({day_pct:+.2f}%)")
            self.day_pnl_label.setStyleSheet(
                "font-weight: bold; font-size: 12px; padding: 4px 8px; "
                "background-color: #111318; border-radius: 4px; color: " +
                ("#00aa55" if day_pnl > 0 else "#ff4d6d" if day_pnl < 0 else "#e0e0e0") + ";")

            total_pct = (total_pnl / total_invested * 100) if total_invested else 0
            self.total_pnl_label.setText(
                f"Total P&L: ₹{total_pnl:,.2f} ({total_pct:+.2f}%)")
            self.total_pnl_label.setStyleSheet(
                "font-weight: bold; font-size: 12px; padding: 4px 8px; "
                "background-color: #111318; border-radius: 4px; color: " +
                ("#00aa55" if total_pnl > 0 else "#ff4d6d" if total_pnl < 0 else "#e0e0e0") + ";")

            self.log(f"Holdings refreshed. Total P&L: ₹{total_pnl:,.2f}", category="Success")
        except Exception as e:
            self.log(f"Summary error: {e}", category="Error", error=True)


# ========== Positions Tab ==========
class PositionsTab(BaseTab):
    def __init__(self, client, log_callback):
        super().__init__(log_callback)
        self.client = client
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(8)

        self.net_pnl_label    = QLabel("Net P&L: --")
        self.unrealized_label = QLabel("Unrealized P&L: --")
        compact_style = "font-weight: bold; font-size: 12px; padding: 4px 8px; background-color: #111318; border-radius: 4px;"
        for label in [self.net_pnl_label, self.unrealized_label]:
            label.setStyleSheet(compact_style)
            summary_layout.addWidget(label)
        layout.addLayout(summary_layout)

        self.table = QTableWidget()
        self.table.verticalHeader().setDefaultSectionSize(24)
        layout.addWidget(self.table)

        btn = QPushButton("Refresh Positions")
        btn.setObjectName("neutralBtn")
        btn.clicked.connect(self.refresh_data)
        layout.addWidget(btn)
        self.setLayout(layout)

    def refresh_data(self):
        self.log("Fetching positions...", category="Info")
        self._run_worker(
            self.client.positions.get_net_positions,
            self.update_table,
            lambda err: self.log(f"Error: {err}", category="Error", error=True)
        )

    def update_table(self, positions):
        if not positions:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.net_pnl_label.setText("Net P&L: --")
            self.unrealized_label.setText("Unrealized P&L: --")
            self.log("No open positions.", category="Info")
            return

        cols    = ['tradingsymbol', 'quantity', 'average_price', 'last_price', 'pnl', 'unrealised']
        headers = ['Symbol', 'Qty', 'Avg Price', 'LTP', 'P&L', 'Unrealized']
        self.table.setRowCount(len(positions))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        total_pnl        = 0.0
        total_unrealized = 0.0
        for i, pos in enumerate(positions):
            pnl        = pos.get('pnl', 0.0)
            unrealised = pos.get('unrealised', 0.0)
            total_pnl        += pnl
            total_unrealized += unrealised

            for j, key in enumerate(cols):
                val  = pos.get(key, 0)
                if isinstance(val, float):
                    val = f"{val:.2f}"
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if j in (4, 5):   # P&L / Unrealized
                    try:
                        num_val = float(val)
                        if num_val > 0:
                            item.setForeground(QColor("#00aa55"))
                        elif num_val < 0:
                            item.setForeground(Qt.GlobalColor.red)
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                    except Exception:
                        pass
                self.table.setItem(i, j, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)

        self._update_summary_card(self.net_pnl_label,    "Net P&L",        total_pnl)
        self._update_summary_card(self.unrealized_label,  "Unrealized P&L", total_unrealized)
        self.log(f"Positions refreshed. Count: {len(positions)}", category="Info")

    def _update_summary_card(self, label, title, value):
        label.setText(f"{title}: ₹{value:,.2f}")
        color = "#00aa55" if value > 0 else "#ff4d6d" if value < 0 else "#e0e0e0"
        label.setStyleSheet(
            f"font-weight: bold; font-size: 12px; padding: 4px 8px; "
            f"background-color: #111318; border-radius: 4px; color: {color};")


# ========== Orders Tab ==========
class OrdersTab(BaseTab):
    def __init__(self, client, log_callback):
        super().__init__(log_callback)
        self.client = client
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # Filter row - more compact
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        self.chk_open      = QCheckBox("Open")
        self.chk_complete  = QCheckBox("Complete")
        self.chk_cancelled = QCheckBox("Cancelled")
        self.chk_rejected  = QCheckBox("Rejected")
        self.chk_open.setChecked(True)

        filter_layout.addWidget(QLabel("Status:"))
        for cb in [self.chk_open, self.chk_complete, self.chk_cancelled, self.chk_rejected]:
            filter_layout.addWidget(cb)

        self.chk_buy  = QCheckBox("Buy")
        self.chk_sell = QCheckBox("Sell")
        self.chk_buy.setChecked(True)
        self.chk_sell.setChecked(True)
        filter_layout.addWidget(QLabel("Type:"))
        filter_layout.addWidget(self.chk_buy)
        filter_layout.addWidget(self.chk_sell)

        self.chk_mis = QCheckBox("MIS")
        self.chk_cnc = QCheckBox("CNC")
        self.chk_mis.setChecked(True)
        filter_layout.addWidget(QLabel("Product:"))
        filter_layout.addWidget(self.chk_mis)
        filter_layout.addWidget(self.chk_cnc)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        for cb in [self.chk_open, self.chk_complete, self.chk_cancelled, self.chk_rejected,
                   self.chk_buy, self.chk_sell, self.chk_mis, self.chk_cnc]:
            cb.stateChanged.connect(self.refresh_data)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setDefaultSectionSize(24)
        layout.addWidget(self.table)

        btn_refresh = QPushButton("Refresh Orders")
        btn_refresh.setObjectName("neutralBtn")
        btn_refresh.clicked.connect(self.refresh_data)
        layout.addWidget(btn_refresh)
        self.setLayout(layout)

    def refresh_data(self):
        self.log("Fetching all orders...", category="Info")
        self._run_worker(
            self.client.orders.get_all_orders,
            self.update_table,
            lambda err: self.log(f"Error: {err}", category="Error", error=True)
        )

    def update_table(self, orders):
        if not orders:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.log("No orders found.", category="Info")
            return

        filtered = []
        for o in orders:
            status     = o.get('status', '')
            trans_type = o.get('transaction_type', '')
            product    = o.get('product', '')

            if status in ('OPEN', 'TRIGGER PENDING', 'PENDING', 'AMO REQ RECEIVED'):
                if not self.chk_open.isChecked():
                    continue
            elif status == 'COMPLETE':
                if not self.chk_complete.isChecked():
                    continue
            elif status in ('CANCELLED', 'CANCELLED AMO'):
                if not self.chk_cancelled.isChecked():
                    continue
            elif status == 'REJECTED':
                if not self.chk_rejected.isChecked():
                    continue
            else:
                continue

            if trans_type == 'BUY'  and not self.chk_buy.isChecked():  continue
            if trans_type == 'SELL' and not self.chk_sell.isChecked(): continue
            if product == 'MIS' and not self.chk_mis.isChecked(): continue
            if product == 'CNC' and not self.chk_cnc.isChecked(): continue

            filtered.append(o)

        if not filtered:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.log("No orders match current filters.", category="Info")
            return

        cols    = ['order_id', 'order_timestamp', 'tradingsymbol', 'transaction_type',
                   'order_type', 'quantity', 'filled_quantity', 'price',
                   'average_price', 'status', 'product']
        headers = ['Order ID', 'Time', 'Symbol', 'Type', 'Order Type',
                   'Qty', 'Filled', 'Price', 'Avg Price', 'Status', 'Product']

        filtered.sort(key=lambda x: x.get('order_timestamp', ''), reverse=True)

        self.table.setRowCount(len(filtered))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        right_align_skip = {0, 2, 3, 4, 9, 10}
        for i, order in enumerate(filtered):
            for j, key in enumerate(cols):
                val  = order.get(key, '')
                if isinstance(val, float):
                    val = f"{val:.2f}"
                item = QTableWidgetItem(str(val))
                if j not in right_align_skip:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.log(f"Orders refreshed. Total: {len(filtered)}", category="Info")


# ========== Funds Tab ==========
class FundsTab(BaseTab):
    def __init__(self, client, log_callback):
        super().__init__(log_callback)
        self.client = client
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        card_layout = QHBoxLayout()
        card_layout.setSpacing(12)

        def make_card(title, attr, color):
            card = QFrame()
            card.setStyleSheet(
                "background-color: #111318; border-radius: 6px; padding: 4px 8px;")
            vbox = QVBoxLayout(card)
            vbox.setSpacing(2)
            lbl  = QLabel(title)
            lbl.setStyleSheet("font-weight: bold; font-size: 10px; color: #4a5060;")
            val = QLabel("--")
            val.setStyleSheet(
                f"font-weight: bold; font-size: 14px; color: {color};")
            vbox.addWidget(lbl)
            vbox.addWidget(val)
            setattr(self, attr, val)
            return card

        card_layout.addWidget(make_card("Available Margin",  "available_value",  "#00e5a0"))
        card_layout.addWidget(make_card("Used Margin",       "used_value",        "#ff4d6d"))
        card_layout.addWidget(make_card("Opening Balance",   "opening_value",     "#4ecdc4"))
        card_layout.addStretch()
        layout.addLayout(card_layout)

        btn_refresh = QPushButton("Refresh Funds")
        btn_refresh.setObjectName("neutralBtn")
        btn_refresh.clicked.connect(self.refresh_data)
        layout.addWidget(btn_refresh)
        layout.addStretch()
        self.setLayout(layout)

    def refresh_data(self):
        self.log("Fetching margin details...", category="Info")
        self._run_worker(
            self.client.get_margin_summary,
            self.update_funds,
            lambda err: self.log(f"Error: {err}", category="Error", error=True)
        )

    def update_funds(self, summary: Dict):
        self.available_value.setText(f"₹{summary.get('available_margin', 0):,.2f}")
        self.used_value.setText(     f"₹{summary.get('used_margin',       0):,.2f}")
        self.opening_value.setText(  f"₹{summary.get('opening_balance',   0):,.2f}")
        self.log("Funds updated.", category="Success")


# ========== Quick Order Dialog (Compact) ==========
class QuickOrderDialog(QDialog):
    def __init__(self, client, log_callback, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Order")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setMaximumWidth(550)

        self.client         = client
        self.log            = log_callback
        self.current_ltp    = None
        self.current_symbol = None
        self.retry_count    = 0
        self.workers        = []

        self.init_ui()
        self.fetch_initial_margin()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Symbol row
        symbol_layout = QHBoxLayout()
        self.symbol_combo = QComboBox()
        self.symbol_combo.setEditable(True)
        self.symbol_combo.addItems(self.client.symbols)
        self.symbol_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = self.symbol_combo.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.symbol_combo.lineEdit().returnPressed.connect(self.fetch_ltp)
        symbol_layout.addWidget(QLabel("Symbol:"), 1)
        symbol_layout.addWidget(self.symbol_combo, 3)

        self.fetch_ltp_btn = QPushButton("Fetch LTP")
        self.fetch_ltp_btn.setStyleSheet("""
            QPushButton {
                background-color: #5dade2; color: white;
                font-weight: bold; border-radius: 4px; padding: 4px 8px;
            }
            QPushButton:hover { background-color: #3498db; }
        """)
        self.fetch_ltp_btn.clicked.connect(self.fetch_ltp)
        symbol_layout.addWidget(self.fetch_ltp_btn)
        layout.addLayout(symbol_layout)

        # LTP display
        self.ltp_label = QLabel("LTP : --")
        self.ltp_label.setStyleSheet("""
            font-weight: bold; font-size: 12px; padding: 4px;
            background-color: #000000; border-radius: 4px; color: white;
        """)
        layout.addWidget(self.ltp_label)

        # Risk Management Group (compact)
        risk_group = QGroupBox("Risk Management")
        risk_layout = QFormLayout()
        risk_layout.setSpacing(4)
        risk_layout.setContentsMargins(4, 4, 4, 4)

        self.capital_spin = QDoubleSpinBox()
        self.capital_spin.setRange(0, 10_000_000)
        self.capital_spin.setPrefix("₹")
        self.capital_spin.setSingleStep(1000)
        self.capital_spin.setDecimals(2)
        self.capital_spin.valueChanged.connect(self.on_capital_changed)
        risk_layout.addRow("Capital:", self.capital_spin)

        self.max_sl_spin = QDoubleSpinBox()
        self.max_sl_spin.setRange(0, 10_000_000)
        self.max_sl_spin.setPrefix("₹")
        self.max_sl_spin.setSingleStep(100)
        self.max_sl_spin.setDecimals(2)
        self.max_sl_spin.valueChanged.connect(self.update_quantity)
        risk_layout.addRow("Max SL:", self.max_sl_spin)

        self.sl_percent_spin = QDoubleSpinBox()
        self.sl_percent_spin.setRange(0.1, 10.0)
        self.sl_percent_spin.setValue(1.0)
        self.sl_percent_spin.setSuffix("%")
        self.sl_percent_spin.setSingleStep(0.1)
        self.sl_percent_spin.valueChanged.connect(self.update_quantity)
        risk_layout.addRow("SL %:", self.sl_percent_spin)

        risk_group.setLayout(risk_layout)
        layout.addWidget(risk_group)

        # Quantity (auto)
        qty_layout = QHBoxLayout()
        qty_layout.addWidget(QLabel("Quantity (auto):"))
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 10000)
        self.quantity_spin.setReadOnly(True)
        self.quantity_spin.setStyleSheet("background-color: #2c2c2c; color: #e0e0e0;")
        qty_layout.addWidget(self.quantity_spin)
        qty_layout.addStretch()
        layout.addLayout(qty_layout)

        # BUY/SELL buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.buy_btn = QPushButton("BUY")
        self.buy_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white;
                font-weight: bold; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.buy_btn.clicked.connect(lambda: self.place_order("BUY"))

        self.sell_btn = QPushButton("SELL")
        self.sell_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c; color: white;
                font-weight: bold; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.sell_btn.clicked.connect(lambda: self.place_order("SELL"))

        btn_layout.addWidget(self.buy_btn)
        btn_layout.addWidget(self.sell_btn)
        layout.addLayout(btn_layout)

        # Exit Order Settings (compact)
        exit_group = QGroupBox("Exit Order Settings")
        exit_layout = QVBoxLayout()
        exit_layout.setSpacing(4)
        exit_layout.setContentsMargins(4, 4, 4, 4)

        target_layout = QHBoxLayout()
        self.target_radio = QRadioButton("Target")
        self.target_radio.setChecked(False)
        target_layout.addWidget(self.target_radio)
        target_layout.addWidget(QLabel("Target %:"))
        self.target_percent_spin = QDoubleSpinBox()
        self.target_percent_spin.setRange(0.1, 10.0)
        self.target_percent_spin.setValue(1.0)
        self.target_percent_spin.setSuffix("%")
        self.target_percent_spin.setSingleStep(0.1)
        self.target_percent_spin.setFixedWidth(90)
        target_layout.addWidget(self.target_percent_spin)
        target_layout.addStretch()
        exit_layout.addLayout(target_layout)

        sl_layout = QHBoxLayout()
        self.sl_radio = QRadioButton("Stop Loss")
        self.sl_radio.setChecked(True)
        sl_layout.addWidget(self.sl_radio)
        sl_layout.addWidget(QLabel("SL %:"))
        sl_layout.addWidget(self.sl_percent_spin)   # reuse
        sl_layout.addStretch()
        exit_layout.addLayout(sl_layout)

        exit_group.setLayout(exit_layout)
        layout.addWidget(exit_group)

        # Convert button
        self.convert_btn = QPushButton("Convert Target ↔ SL")
        self.convert_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12; color: white;
                font-weight: bold; border-radius: 4px; padding: 4px;
            }
            QPushButton:hover { background-color: #e67e22; }
        """)
        self.convert_btn.clicked.connect(self.convert_target_sl)
        layout.addWidget(self.convert_btn)

        # Toggle main window button
        self.toggle_main_btn = QPushButton("Minimize Main Window")
        self.toggle_main_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a5a5a; color: white;
                font-weight: bold; border-radius: 4px; padding: 4px;
            }
            QPushButton:hover { background-color: #7a7a7a; }
        """)
        self.toggle_main_btn.clicked.connect(self.toggle_main_window)
        layout.addWidget(self.toggle_main_btn)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("padding: 2px; color: #e0e0e0; font-size: 10px;")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    # ── Margin & Capital ──────────────────────────────────────────────────
    def fetch_initial_margin(self):
        self._run_worker(
            self.client.get_margin_summary,
            self.on_margin_fetched,
            lambda err: self.log(f"Could not fetch margin: {err}", category="Error")
        )

    def on_margin_fetched(self, summary):
        available = summary.get('available_margin', 0.0)
        self.capital_spin.setValue(available)
        default_max_sl = available * 0.01
        self.max_sl_spin.setValue(default_max_sl)
        self.log(f"Capital set to ₹{available:,.2f}, Max SL = ₹{default_max_sl:,.2f}",
                 category="Info")
        self.update_quantity()

    def on_capital_changed(self, new_capital):
        new_max_sl = new_capital * 0.01
        self.max_sl_spin.blockSignals(True)
        self.max_sl_spin.setValue(new_max_sl)
        self.max_sl_spin.blockSignals(False)
        self.update_quantity()

    # ── Quantity calculation (uses SL %) ──────────────────────────────────
    def update_quantity(self):
        if self.current_ltp is None or self.current_ltp <= 0:
            self.quantity_spin.setValue(1)
            return

        max_sl = self.max_sl_spin.value()
        sl_pct = self.sl_percent_spin.value()
        if max_sl <= 0 or sl_pct <= 0:
            self.quantity_spin.setValue(1)
            return

        risk_per_share = self.current_ltp * (sl_pct / 100.0)
        if risk_per_share <= 0:
            self.quantity_spin.setValue(1)
            return

        qty = int(max_sl / risk_per_share)
        qty = max(qty, 1)
        self.quantity_spin.setValue(qty)

    # ── LTP fetch ─────────────────────────────────────────────────────────
    def fetch_ltp(self):
        symbol = self.symbol_combo.currentText().strip().upper()
        if not symbol:
            QMessageBox.warning(self, "Input Error", "Please select a symbol.")
            return
        self.current_symbol = symbol
        self.status_label.setText("Fetching LTP...")
        self.fetch_ltp_btn.setEnabled(False)
        self._run_worker(
            self.client.fetch_ltp,
            self.on_ltp_fetched,
            self.on_ltp_error,
            symbol
        )

    def on_ltp_fetched(self, result):
        ltp, error = result
        self.fetch_ltp_btn.setEnabled(True)
        if ltp:
            self.current_ltp = ltp
            self.ltp_label.setText(f"LTP : ₹{ltp:,.2f}")
            self.status_label.setText("Ready")
            self.log(f"Quick order LTP fetched: ₹{ltp:,.2f}", category="Info")
            self.update_quantity()
        else:
            self.status_label.setText(f"LTP fetch failed: {error}")
            self.log(f"Quick order LTP error: {error}", category="Error", error=True)

    def on_ltp_error(self, err):
        self.fetch_ltp_btn.setEnabled(True)
        self.status_label.setText(f"Error: {err}")
        self.log(f"Quick order LTP error: {err}", category="Error", error=True)

    # ── Order placement (unchanged logic) ─────────────────────────────────
    def place_order(self, transaction_type):
        if not self.current_symbol:
            QMessageBox.warning(self, "Input Error", "Please select a symbol and fetch LTP.")
            return
        if self.current_ltp is None:
            QMessageBox.warning(self, "LTP Missing", "Please fetch LTP first.")
            return

        quantity = self.quantity_spin.value()
        is_target = self.target_radio.isChecked()
        mode = "Target" if is_target else "Stop Loss"
        exit_pct = self.target_percent_spin.value() if is_target else self.sl_percent_spin.value()

        # confirm = QMessageBox.question(
        #     self, "Confirm Order",
        #     f"Place {transaction_type} market order?\n\n"
        #     f"  Symbol   : {self.current_symbol}\n"
        #     f"  Quantity : {quantity}\n"
        #     f"  LTP      : ₹{self.current_ltp:,.2f}\n"
        #     f"  Exit as  : {mode} @ {exit_pct:.1f}%",
        #     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        # )
        # if confirm != QMessageBox.StandardButton.Yes:
        #     return

        self.buy_btn.setEnabled(False)
        self.sell_btn.setEnabled(False)
        self.status_label.setText(f"Placing {transaction_type} market order...")
        self.log(
            f"Quick order: {transaction_type} {quantity} {self.current_symbol} | "
            f"Exit: {mode} @ {exit_pct:.1f}%",
            category="Info"
        )

        func = self.client.buy_market if transaction_type == "BUY" else self.client.sell_market
        self._run_worker(
            func,
            lambda res: self.on_main_order_placed(res, transaction_type, quantity, is_target),
            self._on_order_btn_error,
            self.current_symbol, quantity, "NSE"
        )

    def _on_order_btn_error(self, err):
        self.buy_btn.setEnabled(True)
        self.sell_btn.setEnabled(True)
        self.on_order_error(err)

    def on_main_order_placed(self, result, transaction_type, quantity, is_target):
        self.buy_btn.setEnabled(True)
        self.sell_btn.setEnabled(True)

        if result.get('status') != 'success':
            error_msg = result.get('message', str(result))
            self.status_label.setText(f"Order failed: {error_msg[:50]}")
            self.log(f"Quick order failed: {error_msg}", category="Error", error=True)
            QMessageBox.warning(self, "Order Failed", error_msg)
            return

        order_id = result.get('data', {}).get('order_id', 'N/A')
        mode = "Target" if is_target else "Stop Loss"
        self.status_label.setText(
            f"{transaction_type} placed (ID: {order_id}). "
            f"Waiting for fill to place {mode}...")
        self.log(
            f"Quick order {transaction_type} placed. ID: {order_id}. "
            f"Will place {mode} @ {self.target_percent_spin.value() if is_target else self.sl_percent_spin.value():.1f}%",
            category="Success"
        )

        self.retry_count = 0
        QTimer.singleShot(1500, lambda: self.fetch_position_with_retry(
            transaction_type, quantity, is_target))

    # ── Position polling (unchanged) ──────────────────────────────────────
    def fetch_position_with_retry(self, transaction_type, quantity, is_target, delay=1500):
        self._run_worker(
            self.client.positions.get_net_positions,
            lambda positions: self.on_positions_fetched(
                positions, transaction_type, quantity, is_target, delay),
            lambda err: self.on_position_fetch_error(
                err, transaction_type, quantity, is_target, delay)
        )

    def on_positions_fetched(self, positions, transaction_type, quantity, is_target, delay):
        pos = self._find_position(positions)
        if not pos:
            if self.retry_count < 5:
                self.retry_count += 1
                self.log(
                    f"Position not yet updated, retry {self.retry_count}/5...",
                    category="Info")
                QTimer.singleShot(delay, lambda: self.fetch_position_with_retry(
                    transaction_type, quantity, is_target, delay + 500))
            else:
                self.status_label.setText("Position not found after 5 retries")
                self.log("Could not find open position to place exit order",
                         category="Error", error=True)
            return

        avg_price = self._resolve_avg_price(pos)
        if avg_price <= 0:
            self.status_label.setText("Invalid average price, cannot place exit order")
            self.log("Invalid average price", category="Error", error=True)
            return

        self.place_target_sl_order(avg_price, transaction_type, quantity, is_target)

    def on_position_fetch_error(self, err, transaction_type, quantity, is_target, delay):
        if self.retry_count < 5:
            self.retry_count += 1
            self.log(f"Position fetch error, retry {self.retry_count}/5...",
                     category="Warning")
            QTimer.singleShot(delay, lambda: self.fetch_position_with_retry(
                transaction_type, quantity, is_target, delay + 500))
        else:
            self.log(f"Failed to fetch position after 5 retries: {err}",
                     category="Error", error=True)
            self.status_label.setText("Position fetch failed")

    # ── Place exit order (unchanged) ──────────────────────────────────────
    def place_target_sl_order(self, avg_price, transaction_type, quantity, is_target):
        if is_target:
            percent = self.target_percent_spin.value() / 100.0
            order_desc = "Target"
        else:
            percent = self.sl_percent_spin.value() / 100.0
            order_desc = "Stop Loss"

        if transaction_type == "BUY":
            exit_transaction = "SELL"
            if is_target:
                order_type_api = "LIMIT"
                price = round(avg_price * (1.0 + percent), 2)
                trigger_price = 0
            else:
                order_type_api = "SL"
                price = round(avg_price * (1.0 - percent), 2)
                trigger_price = round(price * 1.001, 2)
        else:  # SELL
            exit_transaction = "BUY"
            if is_target:
                order_type_api = "LIMIT"
                price = round(avg_price * (1.0 - percent), 2)
                trigger_price = 0
            else:
                order_type_api = "SL"
                price = round(avg_price * (1.0 + percent), 2)
                trigger_price = round(price * 0.999, 2)

        payload = {
            'exchange': "NSE",
            'tradingsymbol': self.current_symbol,
            'transaction_type': exit_transaction,
            'quantity': quantity,
            'product': "MIS",
            'validity': "DAY",
            'variety': "regular",
            'order_type': order_type_api,
            'price': price,
            'trigger_price': trigger_price,
            'disclosed_quantity': 0,
            'squareoff': 0,
            'stoploss': 0,
            'trailing_stoploss': 0,
            'user_id': self.client.trading.user_id
        }

        desc = (f"Placing {order_desc}: {exit_transaction} {quantity} "
                f"{self.current_symbol} @ ₹{price:.2f}" +
                (f" (trigger ₹{trigger_price:.2f})" if trigger_price else ""))
        self.status_label.setText(desc)
        self.log(desc, category="Info")

        self._run_worker(
            self.client.trading._place_order,
            lambda res: self.on_target_sl_placed(res, order_desc),
            lambda err: self.on_order_error(err),
            "regular", payload
        )

    def on_target_sl_placed(self, result, order_desc):
        if result.get('status') == 'success':
            oid = result.get('data', {}).get('order_id', 'N/A')
            msg = f"{order_desc} order placed. ID: {oid}"
            self.status_label.setText(msg)
            self.log(f"Quick order {order_desc} placed. ID: {oid}", category="Success")
        else:
            error_msg = result.get('message', str(result))
            self.status_label.setText(f"{order_desc} failed: {error_msg[:60]}")
            self.log(f"Quick order {order_desc} failed: {error_msg}",
                     category="Error", error=True)

    def on_order_error(self, err):
        self.status_label.setText(f"Error: {err}")
        self.log(f"Quick order error: {err}", category="Error", error=True)

    # ── Convert Target ↔ SL (unchanged) ───────────────────────────────────
    def convert_target_sl(self):
        if not self.current_symbol:
            QMessageBox.warning(self, "Input Error", "Please select a symbol first.")
            return
        self.status_label.setText("Fetching open orders for conversion...")
        self._run_worker(
            self.client.orders.get_all_orders,
            self.do_convert,
            lambda err: self.on_order_error(err)
        )

    def do_convert(self, orders):
        open_statuses = ['OPEN', 'TRIGGER PENDING', 'PENDING']
        symbol_orders = [
            o for o in orders
            if o.get('tradingsymbol') == self.current_symbol
            and o.get('status') in open_statuses
        ]
        target_order = next((o for o in symbol_orders if o.get('order_type') == 'LIMIT'), None)
        sl_order     = next((o for o in symbol_orders if o.get('order_type') == 'SL'),    None)

        if not target_order and not sl_order:
            self.status_label.setText("No open target or SL order found.")
            self.log("No open target/SL order to convert", category="Warning")
            return

        if target_order:
            self.log(f"Cancelling target order {target_order['order_id']}", category="Info")
            self._run_worker(
                self.client.orders.cancel_order,
                lambda res: self.after_cancel_place_sl(res),
                lambda err: self.on_order_error(err),
                target_order['order_id'], target_order.get('variety', 'regular')
            )
        else:
            self.log(f"Cancelling SL order {sl_order['order_id']}", category="Info")
            self._run_worker(
                self.client.orders.cancel_order,
                lambda res: self.after_cancel_place_target(res),
                lambda err: self.on_order_error(err),
                sl_order['order_id'], sl_order.get('variety', 'regular')
            )

    def after_cancel_place_sl(self, cancel_result):
        if cancel_result.get('status') != 'success':
            self.status_label.setText("Cancel failed")
            self.log("Failed to cancel target order", category="Error", error=True)
            return
        self._run_worker(
            self.client.positions.get_net_positions,
            self.place_sl_from_position,
            lambda err: self.on_order_error(err)
        )

    def place_sl_from_position(self, positions):
        pos = self._find_position(positions)
        if not pos:
            self.status_label.setText("No open position found for SL")
            self.log("No open position to place SL", category="Error", error=True)
            return

        avg_price, quantity, exit_type = self._extract_pos_info(pos)
        percent = self.sl_percent_spin.value() / 100.0

        if exit_type == "SELL":
            sl_price = round(avg_price * (1.0 - percent), 2)
            trigger_price = round(sl_price * 1.001, 2)
        else:
            sl_price = round(avg_price * (1.0 + percent), 2)
            trigger_price = round(sl_price * 0.999, 2)

        payload = {
            'exchange': "NSE",
            'tradingsymbol': self.current_symbol,
            'transaction_type': exit_type,
            'quantity': quantity,
            'product': "MIS",
            'validity': "DAY",
            'variety': "regular",
            'order_type': "SL",
            'price': sl_price,
            'trigger_price': trigger_price,
            'disclosed_quantity': 0,
            'squareoff': 0,
            'stoploss': 0,
            'trailing_stoploss': 0,
            'user_id': self.client.trading.user_id
        }
        self.status_label.setText(f"Placing SL order @ ₹{sl_price:.2f}...")
        self._run_worker(
            self.client.trading._place_order,
            lambda res: self.on_target_sl_placed(res, "Stop Loss"),
            lambda err: self.on_order_error(err),
            "regular", payload
        )

    def after_cancel_place_target(self, cancel_result):
        if cancel_result.get('status') != 'success':
            self.status_label.setText("Cancel failed")
            self.log("Failed to cancel SL order", category="Error", error=True)
            return
        self._run_worker(
            self.client.positions.get_net_positions,
            self.place_target_from_position,
            lambda err: self.on_order_error(err)
        )

    def place_target_from_position(self, positions):
        pos = self._find_position(positions)
        if not pos:
            self.status_label.setText("No open position found for target")
            self.log("No open position to place target", category="Error", error=True)
            return

        avg_price, quantity, exit_type = self._extract_pos_info(pos)
        percent = self.target_percent_spin.value() / 100.0

        price = (round(avg_price * (1.0 + percent), 2)
                 if exit_type == "SELL"
                 else round(avg_price * (1.0 - percent), 2))

        payload = {
            'exchange': "NSE",
            'tradingsymbol': self.current_symbol,
            'transaction_type': exit_type,
            'quantity': quantity,
            'product': "MIS",
            'validity': "DAY",
            'variety': "regular",
            'order_type': "LIMIT",
            'price': price,
            'trigger_price': 0,
            'disclosed_quantity': 0,
            'squareoff': 0,
            'stoploss': 0,
            'trailing_stoploss': 0,
            'user_id': self.client.trading.user_id
        }
        self.status_label.setText(f"Placing target order @ ₹{price:.2f}...")
        self._run_worker(
            self.client.trading._place_order,
            lambda res: self.on_target_sl_placed(res, "Target"),
            lambda err: self.on_order_error(err),
            "regular", payload
        )

    # ── Helpers (unchanged) ───────────────────────────────────────────────
    def _find_position(self, positions):
        for p in positions:
            if p.get('tradingsymbol') == self.current_symbol:
                if (p.get('quantity', 0) != 0
                        or p.get('buy_quantity',  0) != 0
                        or p.get('sell_quantity', 0) != 0):
                    return p
        return None

    def _resolve_avg_price(self, pos):
        avg = pos.get('average_price', 0.0)
        if avg <= 0:
            avg = pos.get('buy_price', 0.0) or pos.get('sell_price', 0.0)
        if avg <= 0 and self.current_ltp:
            avg = self.current_ltp
            self.log(f"avg_price was 0, using LTP ₹{avg:.2f} as fallback",
                     category="Warning")
        return avg

    def _extract_pos_info(self, pos):
        avg_price = self._resolve_avg_price(pos)
        net_qty   = pos.get('quantity',      0)
        buy_qty   = pos.get('buy_quantity',  0)
        sell_qty  = pos.get('sell_quantity', 0)
        quantity  = abs(net_qty) or abs(buy_qty) or abs(sell_qty)
        exit_type = "SELL" if (net_qty > 0 or buy_qty > 0) else "BUY"
        return avg_price, quantity, exit_type

    # ── Worker management ─────────────────────────────────────────────────
    def _run_worker(self, func, finished_callback, error_callback, *args, **kwargs):
        worker = ApiWorker(func, *args, **kwargs)
        worker.finished.connect(finished_callback)
        worker.error.connect(error_callback)
        worker.start()
        self.workers.append(worker)
        worker.finished.connect(lambda _=None: self._cleanup_workers())
        worker.error.connect(lambda _=None: self._cleanup_workers())

    def _cleanup_workers(self):
        self.workers = [w for w in self.workers if w.isRunning()]

    def toggle_main_window(self):
        main_window = self.parent()
        while main_window and not isinstance(main_window, ZerodhaDashboard):
            main_window = main_window.parent()
        if not main_window:
            return
        if main_window.isMinimized():
            main_window.showNormal()
            main_window.raise_()
            self.toggle_main_btn.setText("Minimize Main Window")
            self.setWindowFlags(
                self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        else:
            main_window.showMinimized()
            self.toggle_main_btn.setText("Restore Main Window")
            self.setWindowFlags(
                self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.show()


# ========== Order Placement Tab (Compact) ==========
class OrderPlacementTab(BaseTab):
    def __init__(self, client, log_callback):
        super().__init__(log_callback)
        self.client           = client
        self.current_ltp      = None
        self.available_margin = 0.0
        self.init_ui()
        self.fetch_margin()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(6, 6, 6, 6)

        # Quick Order button
        quick_btn = QPushButton("Quick Order")
        quick_btn.setObjectName("primaryBtn")
        quick_btn.clicked.connect(self.open_quick_order)
        layout.addWidget(quick_btn)

        # Symbol selection row
        symbol_layout = QHBoxLayout()
        self.symbol_combo = QComboBox()
        self.symbol_combo.setEditable(True)
        self.symbol_combo.addItems(self.client.symbols)
        self.symbol_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = self.symbol_combo.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.symbol_combo.lineEdit().returnPressed.connect(self.fetch_ltp)
        symbol_layout.addWidget(QLabel("Symbol:"), 1)
        symbol_layout.addWidget(self.symbol_combo, 3)
        self.fetch_ltp_btn = QPushButton("Fetch LTP")
        self.fetch_ltp_btn.setObjectName("primaryBtn")
        self.fetch_ltp_btn.clicked.connect(self.fetch_ltp)
        symbol_layout.addWidget(self.fetch_ltp_btn)
        layout.addLayout(symbol_layout)

        # LTP display
        self.ltp_label = QLabel("Last Traded Price: --")
        self.ltp_label.setStyleSheet("font-weight: bold; font-size: 13px; padding: 2px;")
        layout.addWidget(self.ltp_label)

        # Available margin + refresh inline
        margin_layout = QHBoxLayout()
        self.available_margin_label = QLabel("Available Margin: --")
        self.available_margin_label.setStyleSheet(
            "font-weight: bold; color: #00e5a0; background-color: #111318; "
            "padding: 2px 6px; border-radius: 4px;")
        margin_layout.addWidget(self.available_margin_label)
        self.refresh_margin_btn = QPushButton("Refresh")
        self.refresh_margin_btn.setObjectName("neutralBtn")
        self.refresh_margin_btn.clicked.connect(self.fetch_margin)
        margin_layout.addWidget(self.refresh_margin_btn)
        margin_layout.addStretch()
        layout.addLayout(margin_layout)

        # Stock details group (compact)
        self.stock_details_group = QGroupBox("Stock Details")
        self.stock_details_group.setVisible(False)
        details_layout = QGridLayout()
        details_layout.setSpacing(2)
        details_layout.setContentsMargins(4, 4, 4, 4)
        self.open_label   = QLabel("Open: --")
        self.high_label   = QLabel("High: --")
        self.low_label    = QLabel("Low: --")
        self.close_label  = QLabel("Close: --")
        self.volume_label = QLabel("Volume: --")
        self.change_label = QLabel("% Change: --")
        for i, lbl in enumerate([self.open_label, self.high_label, self.low_label,
                                  self.close_label, self.volume_label, self.change_label]):
            details_layout.addWidget(lbl, i // 3, i % 3)
        self.stock_details_group.setLayout(details_layout)
        layout.addWidget(self.stock_details_group)

        # Cancel buttons row
        cancel_layout = QHBoxLayout()
        self.cancel_last_btn = QPushButton("Cancel Last Pending")
        self.cancel_last_btn.setObjectName("dangerBtn")
        self.cancel_last_btn.clicked.connect(self.cancel_last_pending_order)
        self.cancel_all_btn = QPushButton("Cancel All Open")
        self.cancel_all_btn.setObjectName("dangerBtn")
        self.cancel_all_btn.clicked.connect(self.cancel_all_open_orders)
        cancel_layout.addWidget(self.cancel_last_btn)
        cancel_layout.addWidget(self.cancel_all_btn)
        layout.addLayout(cancel_layout)

        # Risk management (compact horizontal layout)
        risk_group = QGroupBox("Risk Management")
        risk_layout = QHBoxLayout()
        risk_layout.setSpacing(8)
        risk_layout.setContentsMargins(4, 4, 4, 4)

        risk_layout.addWidget(QLabel("SL %:"))
        self.sl_percent_spin = QDoubleSpinBox()
        self.sl_percent_spin.setRange(0.1, 100.0)
        self.sl_percent_spin.setValue(1.0)
        self.sl_percent_spin.setSuffix("%")
        self.sl_percent_spin.setSingleStep(0.1)
        self.sl_percent_spin.valueChanged.connect(self.update_quantity)
        risk_layout.addWidget(self.sl_percent_spin)

        risk_layout.addWidget(QLabel("Max SL (₹):"))
        self.max_sl_amt_spin = QDoubleSpinBox()
        self.max_sl_amt_spin.setRange(0, 10_000_000)
        self.max_sl_amt_spin.setPrefix("₹")
        self.max_sl_amt_spin.setSingleStep(100)
        self.max_sl_amt_spin.valueChanged.connect(self.update_quantity)
        risk_layout.addWidget(self.max_sl_amt_spin)

        risk_layout.addStretch()
        risk_group.setLayout(risk_layout)
        layout.addWidget(risk_group)

        # Order parameters group (compact)
        order_group = QGroupBox("Order Parameters")
        order_layout = QFormLayout()
        order_layout.setSpacing(4)
        order_layout.setContentsMargins(4, 4, 4, 4)

        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(["NSE", "BSE"])
        order_layout.addRow("Exchange:", self.exchange_combo)

        self.transaction_combo = QComboBox()
        self.transaction_combo.addItems(["BUY", "SELL"])
        order_layout.addRow("Transaction:", self.transaction_combo)

        self.order_type_combo = QComboBox()
        self.order_type_combo.addItems(["MARKET", "LIMIT", "COVER MARKET", "COVER LIMIT"])
        self.order_type_combo.currentTextChanged.connect(self.on_order_type_changed)
        order_layout.addRow("Order Type:", self.order_type_combo)

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 10000)
        order_layout.addRow("Quantity:", self.quantity_spin)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0.05, 100000)
        self.price_spin.setDecimals(2)
        self.price_spin.setEnabled(False)
        order_layout.addRow("Limit Price (₹):", self.price_spin)

        self.trigger_spin = QDoubleSpinBox()
        self.trigger_spin.setRange(0.05, 100000)
        self.trigger_spin.setDecimals(2)
        self.trigger_spin.setEnabled(False)
        order_layout.addRow("Trigger Price (₹):", self.trigger_spin)

        self.place_btn = QPushButton("Place Order")
        self.place_btn.setObjectName("primaryBtn")
        self.place_btn.clicked.connect(self.place_order)
        order_layout.addRow(self.place_btn)

        order_group.setLayout(order_layout)
        layout.addWidget(order_group)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 10px; padding: 2px;")
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.setLayout(layout)

    def open_quick_order(self):
        dialog = QuickOrderDialog(self.client, self.log, self)
        dialog.exec()

    def on_order_type_changed(self, text):
        self.price_spin.setEnabled(text in ("LIMIT", "COVER LIMIT"))
        self.trigger_spin.setEnabled(text in ("COVER MARKET", "COVER LIMIT"))

    def fetch_margin(self):
        self.log("Fetching available margin...", category="Info")
        self._run_worker(
            self.client.get_margin_summary,
            self.update_margin,
            lambda err: self.log(f"Margin fetch error: {err}", category="Error", error=True)
        )

    def update_margin(self, summary):
        self.available_margin = summary.get('available_margin', 0.0)
        self.available_margin_label.setText(
            f"Available Margin: ₹{self.available_margin:,.2f}")
        self.log(f"Available margin: ₹{self.available_margin:,.2f}", category="Success")
        if self.max_sl_amt_spin.value() <= 0:
            self.max_sl_amt_spin.setValue(self.available_margin * 0.01)
        self.update_quantity()

    def update_quantity(self):
        if not self.current_ltp or self.current_ltp <= 0:
            return
        sl_pct     = self.sl_percent_spin.value()
        max_sl_amt = self.max_sl_amt_spin.value()
        if sl_pct <= 0 or max_sl_amt <= 0:
            return
        sl_per_share = self.current_ltp * (sl_pct / 100)
        qty          = int(max_sl_amt / sl_per_share) if sl_per_share > 0 else 1
        qty          = max(qty, 1)
        if self.available_margin > 0:
            qty = min(qty, max(1, int((self.available_margin / self.current_ltp) * 5)))
        self.quantity_spin.blockSignals(True)
        self.quantity_spin.setValue(qty)
        self.quantity_spin.blockSignals(False)

    def fetch_ltp(self):
        symbol = self.symbol_combo.currentText().strip().upper()
        if not symbol:
            QMessageBox.warning(self, "Input Error", "Please select a symbol.")
            return
        self.log(f"Fetching LTP for {symbol}...", category="Info")
        self.status_label.setText("Fetching LTP...")
        self.fetch_ltp_btn.setEnabled(False)
        self._run_worker(
            self.client.fetch_ltp,
            self.on_ltp_fetched,
            self.on_ltp_error,
            symbol
        )

    def on_ltp_fetched(self, result):
        ltp, error = result
        self.fetch_ltp_btn.setEnabled(True)
        if ltp:
            self.current_ltp = ltp
            self.ltp_label.setText(f"Last Traded Price: ₹{ltp:,.2f}")
            self.log(f"LTP fetched: ₹{ltp:,.2f}", category="Success")
            self.status_label.setText("LTP fetched. Fetching stock details...")
            self._run_worker(
                self.client.fetch_ohlcv,
                self.on_ohlcv_fetched,
                lambda err: self.status_label.setText(f"OHLCV error: {err}"),
                self.symbol_combo.currentText().strip().upper()
            )
            self.update_quantity()
        else:
            msg = f"LTP fetch failed: {error}"
            self.log(msg, category="Error", error=True)
            self.status_label.setText(msg)
            QMessageBox.warning(self, "LTP Error", msg)

    def on_ltp_error(self, err):
        self.fetch_ltp_btn.setEnabled(True)
        self.log(f"LTP error: {err}", category="Error", error=True)
        self.status_label.setText(f"LTP error: {err}")
        QMessageBox.critical(self, "Error", err)

    def on_ohlcv_fetched(self, result):
        ohlcv, error = result
        if ohlcv:
            self.stock_details_group.setVisible(True)
            self.open_label.setText(  f"Open: ₹{ohlcv['open']:,.2f}")
            self.high_label.setText(  f"High: ₹{ohlcv['high']:,.2f}")
            self.low_label.setText(   f"Low: ₹{ohlcv['low']:,.2f}")
            self.close_label.setText( f"Close: ₹{ohlcv['close']:,.2f}")
            vol = ohlcv['volume']
            vol_str = (f"{vol/1_000_000:.2f}M" if vol >= 1_000_000
                       else f"{vol/1_000:.1f}K" if vol >= 1_000
                       else str(vol))
            self.volume_label.setText(f"Volume: {vol_str}")
            pct   = ohlcv['pct_change']
            arrow = "▲" if pct >= 0 else "▼"
            color = "green" if pct >= 0 else "red"
            self.change_label.setText(
                f"% Change: <span style='color:{color};'>{arrow} {abs(pct):.2f}%</span>")
            self.change_label.setTextFormat(Qt.TextFormat.RichText)
            self.status_label.setText("Stock details updated.")
        else:
            self.log(f"OHLCV error: {error}", category="Error", error=True)
            self.status_label.setText(f"OHLCV error: {error}")

    def place_order(self):
        symbol = self.symbol_combo.currentText().strip().upper()
        if not symbol:
            QMessageBox.warning(self, "Input Error", "Please select a symbol.")
            return
        if self.current_ltp is None:
            QMessageBox.warning(self, "LTP Missing", "Please fetch LTP first.")
            return

        exchange     = self.exchange_combo.currentText()
        transaction  = self.transaction_combo.currentText()
        order_type   = self.order_type_combo.currentText()
        quantity     = self.quantity_spin.value()
        limit_price  = self.price_spin.value()   if order_type in ("LIMIT", "COVER LIMIT")    else 0.0
        trigger_price = self.trigger_spin.value() if order_type in ("COVER MARKET", "COVER LIMIT") else 0.0

        if order_type in ("LIMIT", "COVER LIMIT") and limit_price <= 0:
            QMessageBox.warning(self, "Price Error", "Enter a valid limit price.")
            return
        if order_type in ("COVER MARKET", "COVER LIMIT") and trigger_price <= 0:
            QMessageBox.warning(self, "Trigger Error", "Enter a valid trigger price.")
            return

        self.place_btn.setEnabled(False)
        self.status_label.setText("Placing order...")
        self.log(f"Placing {order_type} {transaction} order for {quantity} {symbol}...",
                 category="Info")

        if order_type == "MARKET":
            func = self.client.trading.market
            args = (symbol, transaction, quantity, exchange)
        elif order_type == "LIMIT":
            func = self.client.trading.limit
            args = (symbol, transaction, quantity, limit_price, exchange)
        elif order_type == "COVER MARKET":
            func = self.client.trading.cover_market
            args = (symbol, transaction, quantity, trigger_price, exchange)
        else:
            func = self.client.trading.cover_limit
            args = (symbol, transaction, quantity, limit_price, trigger_price, exchange)

        self._run_worker(
            func,
            lambda res: self.order_placed(res, True),
            lambda err: self.order_placed(err, False),
            *args
        )

    def order_placed(self, result, success):
        self.place_btn.setEnabled(True)
        if success and isinstance(result, dict) and result.get('status') == 'success':
            oid = result.get('data', {}).get('order_id', 'N/A')
            self.status_label.setText(f"Order placed! ID: {oid}")
            self.log(f"✅ Order placed. ID: {oid}", category="Success")
            QMessageBox.information(self, "Success",
                                    f"Order placed successfully.\nOrder ID: {oid}")
        else:
            error_msg = result.get('message', str(result)) if isinstance(result, dict) else str(result)
            self.status_label.setText(f"Order failed: {error_msg[:100]}")
            self.log(f"❌ Order failed: {error_msg}", category="Error", error=True)
            QMessageBox.critical(self, "Order Failed", error_msg)

    def cancel_last_pending_order(self):
        self.log("Fetching open orders to cancel last pending...", category="Info")
        self._run_worker(
            self.client.orders.get_all_orders,
            self._cancel_last_pending,
            lambda err: self.log(f"Failed to fetch orders: {err}",
                                 category="Error", error=True)
        )

    def _cancel_last_pending(self, orders):
        open_statuses = ['OPEN', 'TRIGGER PENDING', 'PENDING', 'AMO REQ RECEIVED']
        open_orders   = [o for o in orders if o.get('status') in open_statuses]
        if not open_orders:
            self.log("No open orders to cancel.", category="Warning")
            QMessageBox.information(self, "No Open Orders",
                                    "There are no pending orders.")
            return
        open_orders.sort(key=lambda x: x.get('order_timestamp', ''), reverse=True)
        last    = open_orders[0]
        oid     = last['order_id']
        variety = last.get('variety', 'regular')
        symbol  = last.get('tradingsymbol', '')
        self.log(f"Cancelling last pending order: {symbol} ({oid})...", category="Info")
        self._run_worker(
            self.client.orders.cancel_order,
            lambda res: self._cancel_result(res, oid, symbol),
            lambda err: self.log(f"Cancel failed: {err}", category="Error", error=True),
            oid, variety
        )

    def cancel_all_open_orders(self):
        self.log("Fetching open orders to cancel all...", category="Info")
        self._run_worker(
            self.client.orders.get_all_orders,
            self._cancel_all_open,
            lambda err: self.log(f"Failed to fetch orders: {err}",
                                 category="Error", error=True)
        )

    def _cancel_all_open(self, orders):
        open_statuses = ['OPEN', 'TRIGGER PENDING', 'PENDING', 'AMO REQ RECEIVED']
        open_orders   = [o for o in orders if o.get('status') in open_statuses]
        if not open_orders:
            self.log("No open orders to cancel.", category="Warning")
            QMessageBox.information(self, "No Open Orders",
                                    "There are no pending orders.")
            return
        self.log(f"Cancelling {len(open_orders)} open order(s)...", category="Info")
        for order in open_orders:
            oid     = order['order_id']
            variety = order.get('variety', 'regular')
            symbol  = order.get('tradingsymbol', '')
            self._run_worker(
                self.client.orders.cancel_order,
                lambda res, o=oid, s=symbol: self._cancel_result(res, o, s),
                lambda err, o=oid: self.log(f"Cancel {o} failed: {err}",
                                            category="Error", error=True),
                oid, variety
            )

    def _cancel_result(self, result, order_id, symbol):
        if result.get('status') == 'success':
            self.log(f"✅ Cancelled {symbol} ({order_id})", category="Success")
        else:
            self.log(f"❌ Failed to cancel {order_id}: "
                     f"{result.get('message', 'Unknown error')}",
                     category="Error", error=True)


# ========== Main Dashboard (Compact) ==========
class ZerodhaDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zerodha Trading Dashboard")
        self.setGeometry(100, 100, 1200, 700)  # smaller default size
        self.load_stylesheet()

        self.client      = ZerodhaClient()
        self.log_entries = []
        self.log_filters = {
            'Error': True, 'Info': True, 'Warning': True, 'Success': True
        }

        central     = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(4)

        # ── Log panel (compact) ───────────────────────────────────────────────
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        self.log_container = QWidget()
        self.log_container.setObjectName("log_container")
        self.log_container.setFixedWidth(260)  # fixed compact width
        log_layout = QVBoxLayout(self.log_container)
        log_layout.setContentsMargins(2, 2, 2, 2)
        log_layout.setSpacing(2)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(4)
        self.chk_error   = QCheckBox("Error")
        self.chk_info    = QCheckBox("Info")
        self.chk_warning = QCheckBox("Warning")
        self.chk_success = QCheckBox("Success")
        for cb in [self.chk_error, self.chk_info, self.chk_warning, self.chk_success]:
            cb.setChecked(True)
            cb.stateChanged.connect(self.apply_log_filter)
            filter_layout.addWidget(cb)
        filter_layout.addStretch()
        log_layout.addLayout(filter_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "font-family: monospace; font-size: 9pt;")  # smaller font
        log_layout.addWidget(self.log_text)

        right_layout.addWidget(self.log_container)
        right_layout.addStretch()

        # ── Tabs ──────────────────────────────────────────────────────────────
        self.tabs           = QTabWidget()
        self.holdings_tab   = HoldingsTab(self.client,   self.add_log_entry)
        self.positions_tab  = PositionsTab(self.client,  self.add_log_entry)
        self.orders_tab     = OrdersTab(self.client,     self.add_log_entry)
        self.funds_tab      = FundsTab(self.client,      self.add_log_entry)
        self.order_tab      = OrderPlacementTab(self.client, self.add_log_entry)

        self.tabs.addTab(self.holdings_tab,  "Holdings")
        self.tabs.addTab(self.positions_tab, "Positions")
        self.tabs.addTab(self.orders_tab,    "Orders")
        self.tabs.addTab(self.funds_tab,     "Funds")
        self.tabs.addTab(self.order_tab,     "Place Order")
        self.tabs.currentChanged.connect(self.on_tab_changed)

        main_layout.addWidget(self.tabs, 4)
        main_layout.addLayout(right_layout, 1)

        self.tabs.setCurrentIndex(4)
        self.add_log_entry("Dashboard initialized (compact UI). Ready.", category="Info")
        self.statusBar().showMessage("Ready")

    def load_stylesheet(self):
        qss_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.qss")
        if os.path.exists(qss_file):
            with open(qss_file, "r") as f:
                self.setStyleSheet(f.read())
        else:
            # fallback compact style
            self.setStyleSheet("""
                QGroupBox { font-weight: bold; border: 1px solid #3c3c3c; border-radius: 4px; margin-top: 8px; padding-top: 4px; }
                QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
                QPushButton { padding: 4px 8px; }
                QTableWidget::item { padding: 2px; }
            """)

    def resizeEvent(self, event):
        # keep log container fixed width, no dynamic resize
        super().resizeEvent(event)

    def on_tab_changed(self, index):
        name = self.tabs.tabText(index)
        if name == "Holdings":  self.holdings_tab.refresh_data()
        elif name == "Positions": self.positions_tab.refresh_data()
        elif name == "Orders":    self.orders_tab.refresh_data()
        elif name == "Funds":     self.funds_tab.refresh_data()

    def add_log_entry(self, message, category="Info", error=False):
        if error and category == "Info":
            category = "Error"
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_entries.append((timestamp, message, category))
        self.apply_log_filter()

    def apply_log_filter(self):
        checks = {
            "Error":   self.chk_error.isChecked(),
            "Info":    self.chk_info.isChecked(),
            "Warning": self.chk_warning.isChecked(),
            "Success": self.chk_success.isChecked(),
        }
        color_map = {
            "Error":   "#ff6b6b",
            "Info":    "#e0e0e0",
            "Warning": "#ffa500",
            "Success": "#4ecdc4",
        }
        prefix_map = {
            "Error":   "❌ ",
            "Info":    "ℹ️ ",
            "Warning": "⚠️ ",
            "Success": "✓ ",
        }
        self.log_text.clear()
        for timestamp, message, category in self.log_entries:
            if not checks.get(category, False):
                continue
            color  = color_map.get(category,  "#e0e0e0")
            prefix = prefix_map.get(category, "")
            self.log_text.append(
                f'<span style="color:{color};">'
                f'[{timestamp}] {prefix}{message}</span>'
            )
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum())


# ========== Entry Point ==========
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ZerodhaDashboard()
    window.show()
    sys.exit(app.exec())