"""
Zerodha Trading Dashboard - PyQt6 GUI
Final layout:
- Log console at top‑right, square (20% width, height = width)
- Tabs on left, filling remaining space
- Default active tab: Place Order
- Funds tab: 3 horizontal cards
- All previous features (auto‑refresh on tab click, fetch LTP on Enter, etc.)
"""

import sys
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QLabel, QPushButton,
    QComboBox, QSpinBox, QDoubleSpinBox, QGroupBox, QFormLayout,
    QMessageBox, QHeaderView, QGridLayout, QTextEdit, QCheckBox,
    QFrame,QLineEdit   
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QEvent
from PyQt6.QtGui import QFont

from trading_client import ZerodhaClient


# ========== Worker Thread ==========
class ApiWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
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
        self.log = log_callback
        self.workers = []

    def _run_worker(self, func, finished_callback, error_callback, *args, **kwargs):
        worker = ApiWorker(func, *args, **kwargs)
        worker.finished.connect(finished_callback)
        worker.error.connect(error_callback)
        worker.finished.connect(self._cleanup_worker)
        worker.error.connect(self._cleanup_worker)
        self.workers.append(worker)
        worker.start()

    def _cleanup_worker(self, *args):
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
        summary_layout = QHBoxLayout()
        self.total_invested_label = QLabel("Total Invested: --")
        self.current_value_label = QLabel("Current Value: --")
        self.day_pnl_label = QLabel("Day's P&L: --")
        self.total_pnl_label = QLabel("Total P&L: --")
        for label in [self.total_invested_label, self.current_value_label,
                      self.day_pnl_label, self.total_pnl_label]:
            label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 8px; background-color: #f0f0f0; border-radius: 5px;")
            summary_layout.addWidget(label)
        layout.addLayout(summary_layout)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        btn_refresh = QPushButton("Refresh Holdings")
        btn_refresh.clicked.connect(self.refresh_data)
        layout.addWidget(btn_refresh)
        self.setLayout(layout)

    def refresh_data(self):
        self.log("Fetching holdings...", category="Info")
        self._run_worker(self.client.get_holdings_df, self.update_table,
                         lambda err: self.log(f"Error: {err}", category="Error", error=True))

    def update_table(self, df: pd.DataFrame):
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.total_invested_label.setText("Total Invested: --")
            self.current_value_label.setText("Current Value: --")
            self.day_pnl_label.setText("Day's P&L: --")
            self.total_pnl_label.setText("Total P&L: --")
            self.log("No holdings found.", category="Info")
            return

        self.table.setRowCount(df.shape[0])
        self.table.setColumnCount(df.shape[1])
        self.table.setHorizontalHeaderLabels(df.columns)
        for i, row in df.iterrows():
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if j not in [0]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        try:
            holdings = self.client.get_holdings()
            total_invested = sum(h['average_price'] * h['quantity'] for h in holdings)
            total_current = sum(h['last_price'] * h['quantity'] for h in holdings)
            day_pnl, total_pnl = self.client.get_holdings_summary()
            self.total_invested_label.setText(f"Total Invested: ₹{total_invested:,.2f}")
            self.current_value_label.setText(f"Current Value: ₹{total_current:,.2f}")
            day_pnl_pct = (day_pnl / total_invested * 100) if total_invested else 0
            self.day_pnl_label.setText(f"Day's P&L: ₹{day_pnl:,.2f} ({day_pnl_pct:+.2f}%)")
            total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
            self.total_pnl_label.setText(f"Total P&L: ₹{total_pnl:,.2f} ({total_pnl_pct:+.2f}%)")
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
        self.table = QTableWidget()
        layout.addWidget(self.table)
        btn = QPushButton("Refresh Positions")
        btn.clicked.connect(self.refresh_data)
        layout.addWidget(btn)
        self.setLayout(layout)

    def refresh_data(self):
        self.log("Fetching positions...", category="Info")
        self._run_worker(self.client.positions.get_net_positions, self.update_table,
                         lambda err: self.log(f"Error: {err}", category="Error", error=True))

    def update_table(self, positions):
        if not positions:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.log("No open positions.", category="Info")
            return
        cols = ['tradingsymbol', 'quantity', 'average_price', 'last_price', 'pnl', 'unrealised']
        headers = ['Symbol', 'Qty', 'Avg Price', 'LTP', 'P&L', 'Unrealized']
        self.table.setRowCount(len(positions))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for i, pos in enumerate(positions):
            for j, key in enumerate(cols):
                val = pos.get(key, 0)
                if isinstance(val, float):
                    val = f"{val:.2f}"
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.log(f"Positions refreshed. Count: {len(positions)}", category="Info")


# ========== Open Orders Tab ==========
class OpenOrdersTab(BaseTab):
    def __init__(self, client, log_callback):
        super().__init__(log_callback)
        self.client = client
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout()
        self.table = QTableWidget()
        layout.addWidget(self.table)
        btn = QPushButton("Refresh Open Orders")
        btn.clicked.connect(self.refresh_data)
        layout.addWidget(btn)
        self.setLayout(layout)

    def refresh_data(self):
        self.log("Fetching open orders...", category="Info")
        self._run_worker(self.client.get_open_orders, self.update_table,
                         lambda err: self.log(f"Error: {err}", category="Error", error=True))

    def update_table(self, df: pd.DataFrame):
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.log("No open orders.", category="Info")
            return
        self.table.setRowCount(df.shape[0])
        self.table.setColumnCount(df.shape[1])
        self.table.setHorizontalHeaderLabels(df.columns)
        for i, row in df.iterrows():
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if j not in [1, 2, 7]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.log(f"Open orders refreshed. Count: {df.shape[0]}", category="Info")


# ========== Funds Tab (simplified, horizontal layout) ==========
class FundsTab(BaseTab):
    def __init__(self, client, log_callback):
        super().__init__(log_callback)
        self.client = client
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout()
        # Horizontal layout for three cards
        card_layout = QHBoxLayout()
        card_layout.setSpacing(20)

        # Available Margin card
        self.available_card = QFrame()
        self.available_card.setStyleSheet("background-color: #111318; border-radius: 8px; padding: 10px;")
        avail_layout = QVBoxLayout(self.available_card)
        avail_label = QLabel("Available Margin")
        avail_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #4a5060;")
        self.available_value = QLabel("--")
        self.available_value.setStyleSheet("font-weight: bold; font-size: 18px; color: #00e5a0;")
        avail_layout.addWidget(avail_label)
        avail_layout.addWidget(self.available_value)
        card_layout.addWidget(self.available_card)

        # Used Margin card
        self.used_card = QFrame()
        self.used_card.setStyleSheet("background-color: #111318; border-radius: 8px; padding: 10px;")
        used_layout = QVBoxLayout(self.used_card)
        used_label = QLabel("Used Margin")
        used_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #4a5060;")
        self.used_value = QLabel("--")
        self.used_value.setStyleSheet("font-weight: bold; font-size: 18px; color: #ff4d6d;")
        used_layout.addWidget(used_label)
        used_layout.addWidget(self.used_value)
        card_layout.addWidget(self.used_card)

        # Opening Balance card
        self.opening_card = QFrame()
        self.opening_card.setStyleSheet("background-color: #111318; border-radius: 8px; padding: 10px;")
        opening_layout = QVBoxLayout(self.opening_card)
        opening_label = QLabel("Opening Balance")
        opening_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #4a5060;")
        self.opening_value = QLabel("--")
        self.opening_value.setStyleSheet("font-weight: bold; font-size: 18px; color: #4ecdc4;")
        opening_layout.addWidget(opening_label)
        opening_layout.addWidget(self.opening_value)
        card_layout.addWidget(self.opening_card)

        card_layout.addStretch()
        layout.addLayout(card_layout)

        btn_refresh = QPushButton("Refresh Funds")
        btn_refresh.clicked.connect(self.refresh_data)
        layout.addWidget(btn_refresh)
        layout.addStretch()
        self.setLayout(layout)

    def refresh_data(self):
        self.log("Fetching margin details...", category="Info")
        self._run_worker(self.client.get_margin_summary, self.update_funds,
                         lambda err: self.log(f"Error: {err}", category="Error", error=True))

    def update_funds(self, summary: Dict):
        self.available_value.setText(f"₹{summary.get('available_margin', 0):,.2f}")
        self.used_value.setText(f"₹{summary.get('used_margin', 0):,.2f}")
        self.opening_value.setText(f"₹{summary.get('opening_balance', 0):,.2f}")
        self.log("Funds updated.", category="Success")


# ========== Order Placement Tab ==========
class OrderPlacementTab(BaseTab):
    def __init__(self, client, log_callback):
        super().__init__(log_callback)
        self.client = client
        self.current_ltp = None
        self.available_margin = 0.0
        self.init_ui()
        self.fetch_margin()

    class SelectOnFocusLineEdit(QLineEdit):
        def focusInEvent(self, event):
            super().focusInEvent(event)
            self.selectAll()

    def init_ui(self):
        layout = QVBoxLayout()

        # Symbol selection
        symbol_layout = QHBoxLayout()
        self.symbol_combo = QComboBox()
        self.symbol_combo.setEditable(True)
        self.symbol_combo.addItems(self.client.symbols)
        self.symbol_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = self.symbol_combo.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        line_edit = self.SelectOnFocusLineEdit()
        self.symbol_combo.setLineEdit(line_edit)
        self.symbol_combo.lineEdit().returnPressed.connect(self.fetch_ltp)
        symbol_layout.addWidget(QLabel("Symbol:"), 1)
        symbol_layout.addWidget(self.symbol_combo, 3)
        self.fetch_ltp_btn = QPushButton("Fetch LTP")
        self.fetch_ltp_btn.clicked.connect(self.fetch_ltp)
        symbol_layout.addWidget(self.fetch_ltp_btn)
        layout.addLayout(symbol_layout)

        # LTP display
        self.ltp_label = QLabel("Last Traded Price: --")
        self.ltp_label.setStyleSheet("font-weight: bold; font-size: 16px; padding: 5px;")
        layout.addWidget(self.ltp_label)

        # Available margin display
        margin_layout = QHBoxLayout()
        self.available_margin_label = QLabel("Available Margin: --")
        self.available_margin_label.setStyleSheet("font-weight: bold; color: #00e5a0; background-color: #111318; padding: 5px; border-radius: 5px;")
        margin_layout.addWidget(self.available_margin_label)
        self.refresh_margin_btn = QPushButton("Refresh Margin")
        self.refresh_margin_btn.clicked.connect(self.fetch_margin)
        margin_layout.addWidget(self.refresh_margin_btn)
        layout.addLayout(margin_layout)

        # Stock details
        self.stock_details_group = QGroupBox("Stock Details (Today)")
        self.stock_details_group.setVisible(False)
        details_layout = QGridLayout()
        self.open_label = QLabel("Open: --")
        self.high_label = QLabel("High: --")
        self.low_label = QLabel("Low: --")
        self.close_label = QLabel("Close: --")
        self.volume_label = QLabel("Volume: --")
        self.change_label = QLabel("% Change: --")
        for i, lbl in enumerate([self.open_label, self.high_label, self.low_label,
                                 self.close_label, self.volume_label, self.change_label]):
            details_layout.addWidget(lbl, i // 3, i % 3, 1, 1)
        self.stock_details_group.setLayout(details_layout)
        layout.addWidget(self.stock_details_group)

        # Cancel buttons row
        cancel_layout = QHBoxLayout()
        self.cancel_last_btn = QPushButton("Cancel Last Pending Order")
        self.cancel_last_btn.clicked.connect(self.cancel_last_pending_order)
        self.cancel_all_btn = QPushButton("Cancel All Open Orders")
        self.cancel_all_btn.clicked.connect(self.cancel_all_open_orders)
        cancel_layout.addWidget(self.cancel_last_btn)
        cancel_layout.addWidget(self.cancel_all_btn)
        layout.addLayout(cancel_layout)

        # Risk management inputs
        risk_group = QGroupBox("Risk Management")
        risk_layout = QGridLayout()
        self.sl_percent_spin = QDoubleSpinBox()
        self.sl_percent_spin.setRange(0.1, 100.0)
        self.sl_percent_spin.setValue(1.0)
        self.sl_percent_spin.setSuffix("%")
        self.sl_percent_spin.setSingleStep(0.1)
        self.sl_percent_spin.valueChanged.connect(self.update_quantity)
        risk_layout.addWidget(QLabel("Stop Loss %:"), 0, 0)
        risk_layout.addWidget(self.sl_percent_spin, 0, 1)

        self.max_sl_amt_spin = QDoubleSpinBox()
        self.max_sl_amt_spin.setRange(0, 10_000_000)
        self.max_sl_amt_spin.setPrefix("₹")
        self.max_sl_amt_spin.setSingleStep(100)
        self.max_sl_amt_spin.valueChanged.connect(self.update_quantity)
        risk_layout.addWidget(QLabel("Max SL Amt (₹):"), 1, 0)
        risk_layout.addWidget(self.max_sl_amt_spin, 1, 1)

        risk_group.setLayout(risk_layout)
        layout.addWidget(risk_group)

        # Order parameters
        order_group = QGroupBox("Order Parameters")
        order_layout = QFormLayout()

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
        self.quantity_spin.valueChanged.connect(self.on_quantity_manually_changed)
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
        self.place_btn.clicked.connect(self.place_order)
        order_layout.addRow(self.place_btn)

        order_group.setLayout(order_layout)
        layout.addWidget(order_group)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.setLayout(layout)

    # def eventFilter(self, obj, event):
    #     if obj == self.symbol_combo.lineEdit() and event.type() == QEvent.Type.FocusIn:
    #         obj.selectAll()
    #     return super().eventFilter(obj, event)

    def on_order_type_changed(self, text):
        is_limit = text in ["LIMIT", "COVER LIMIT"]
        is_cover = text in ["COVER MARKET", "COVER LIMIT"]
        self.price_spin.setEnabled(is_limit)
        self.trigger_spin.setEnabled(is_cover)

    def fetch_margin(self):
        self.log("Fetching available margin...", category="Info")
        self._run_worker(self.client.get_margin_summary, self.update_margin,
                         lambda err: self.log(f"Margin fetch error: {err}", category="Error", error=True))

    def update_margin(self, summary):
        self.available_margin = summary.get('available_margin', 0.0)
        self.available_margin_label.setText(f"Available Margin: ₹{self.available_margin:,.2f}")
        self.log(f"Available margin: ₹{self.available_margin:,.2f}", category="Success")
        if self.max_sl_amt_spin.value() <= 0:
            self.max_sl_amt_spin.setValue(self.available_margin * 0.01)
        self.update_quantity()

    def update_quantity(self):
        if not self.current_ltp or self.current_ltp <= 0:
            return
        sl_pct = self.sl_percent_spin.value()
        max_sl_amt = self.max_sl_amt_spin.value()
        if sl_pct <= 0 or max_sl_amt <= 0:
            return
        sl_per_share = self.current_ltp * (sl_pct / 100)
        qty = int(max_sl_amt / sl_per_share) if sl_per_share > 0 else 1
        if qty < 1:
            qty = 1
        if self.available_margin > 0:
            max_qty_by_cap = int((self.available_margin / self.current_ltp) * 5)
            if max_qty_by_cap < 1:
                max_qty_by_cap = 1
            qty = min(qty, max_qty_by_cap)
        self.quantity_spin.blockSignals(True)
        self.quantity_spin.setValue(qty)
        self.quantity_spin.blockSignals(False)

    def on_quantity_manually_changed(self):
        pass

    def fetch_ltp(self):
        symbol = self.symbol_combo.currentText().strip().upper()
        if not symbol:
            QMessageBox.warning(self, "Input Error", "Please select a symbol.")
            return
        self.log(f"Fetching LTP for {symbol}...", category="Info")
        self.status_label.setText("Fetching LTP...")
        self.fetch_ltp_btn.setEnabled(False)
        self._run_worker(self.client.fetch_ltp, self.on_ltp_fetched,
                         lambda err: self.on_ltp_error(err), symbol)

    def on_ltp_fetched(self, result):
        ltp, error = result
        self.fetch_ltp_btn.setEnabled(True)
        if ltp:
            self.current_ltp = ltp
            self.ltp_label.setText(f"Last Traded Price: ₹{ltp:,.2f}")
            self.log(f"LTP fetched: ₹{ltp:,.2f}", category="Success")
            self.status_label.setText("LTP fetched. Fetching stock details...")
            symbol = self.symbol_combo.currentText().strip().upper()
            self._run_worker(self.client.fetch_ohlcv, self.on_ohlcv_fetched,
                             lambda err: self.status_label.setText(f"OHLCV error: {err}"), symbol)
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
            self.open_label.setText(f"Open: ₹{ohlcv['open']:,.2f}")
            self.high_label.setText(f"High: ₹{ohlcv['high']:,.2f}")
            self.low_label.setText(f"Low: ₹{ohlcv['low']:,.2f}")
            self.close_label.setText(f"Close: ₹{ohlcv['close']:,.2f}")
            vol = ohlcv['volume']
            if vol >= 1_000_000:
                vol_str = f"{vol/1_000_000:.2f}M"
            elif vol >= 1_000:
                vol_str = f"{vol/1_000:.1f}K"
            else:
                vol_str = str(vol)
            self.volume_label.setText(f"Volume: {vol_str}")
            pct = ohlcv['pct_change']
            arrow = "▲" if pct >= 0 else "▼"
            color = "green" if pct >= 0 else "red"
            self.change_label.setText(f"% Change: <span style='color:{color};'>{arrow} {abs(pct):.2f}%</span>")
            self.change_label.setTextFormat(Qt.TextFormat.RichText)
            self.status_label.setText("Stock details updated.")
            self.log(f"OHLCV data updated for {self.symbol_combo.currentText()}", category="Info")
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

        exchange = self.exchange_combo.currentText()
        transaction = self.transaction_combo.currentText()
        order_type = self.order_type_combo.currentText()
        quantity = self.quantity_spin.value()
        limit_price = self.price_spin.value() if order_type in ["LIMIT", "COVER LIMIT"] else 0.0
        trigger_price = self.trigger_spin.value() if order_type in ["COVER MARKET", "COVER LIMIT"] else 0.0

        if order_type in ["LIMIT", "COVER LIMIT"] and limit_price <= 0:
            QMessageBox.warning(self, "Price Error", "Enter a valid limit price.")
            return
        if order_type in ["COVER MARKET", "COVER LIMIT"] and trigger_price <= 0:
            QMessageBox.warning(self, "Trigger Error", "Enter a valid trigger price.")
            return

        self.place_btn.setEnabled(False)
        self.status_label.setText("Placing order...")
        self.log(f"Placing {order_type} {transaction} order for {quantity} {symbol}...", category="Info")

        if order_type == "MARKET":
            func = self.client.trading.market
            args = (symbol, transaction, quantity, exchange)
        elif order_type == "LIMIT":
            func = self.client.trading.limit
            args = (symbol, transaction, quantity, limit_price, exchange)
        elif order_type == "COVER MARKET":
            func = self.client.trading.cover_market
            args = (symbol, transaction, quantity, trigger_price, exchange)
        else:  # COVER LIMIT
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
        if success:
            oid = result.get('data', {}).get('order_id', 'N/A')
            self.status_label.setText(f"Order placed! Order ID: {oid}")
            self.log(f"✅ Order placed successfully. Order ID: {oid}", category="Success")
            QMessageBox.information(self, "Success", f"Order placed successfully.\nOrder ID: {oid}")
        else:
            error_msg = str(result)
            if hasattr(result, 'response') and result.response is not None:
                try:
                    error_json = result.response.json()
                    error_msg = error_json.get('message', error_json.get('error', str(result)))
                except:
                    error_msg = result.response.text if result.response else error_msg
            self.status_label.setText(f"Order failed: {error_msg[:100]}")
            self.log(f"❌ Order failed: {error_msg}", category="Error", error=True)
            QMessageBox.critical(self, "Order Failed", error_msg)

    def cancel_last_pending_order(self):
        self.log("Fetching open orders to cancel last pending...", category="Info")
        self._run_worker(
            self.client.orders.get_all_orders,
            self._cancel_last_pending,
            lambda err: self.log(f"Failed to fetch orders: {err}", category="Error", error=True)
        )

    def _cancel_last_pending(self, orders):
        open_statuses = ['OPEN', 'TRIGGER PENDING', 'PENDING', 'AMO REQ RECEIVED']
        open_orders = [o for o in orders if o.get('status') in open_statuses]
        if not open_orders:
            self.log("No open orders to cancel.", category="Warning")
            QMessageBox.information(self, "No Open Orders", "There are no pending orders.")
            return
        open_orders.sort(key=lambda x: x.get('order_timestamp', ''), reverse=True)
        last_order = open_orders[0]
        order_id = last_order['order_id']
        variety = last_order.get('variety', 'regular')
        symbol = last_order.get('tradingsymbol', '')
        self.log(f"Cancelling last pending order: {symbol} ({order_id})...", category="Info")
        self._run_worker(
            self.client.orders.cancel_order,
            lambda res: self._cancel_result(res, order_id, symbol),
            lambda err: self.log(f"Cancel failed: {err}", category="Error", error=True),
            order_id, variety
        )

    def cancel_all_open_orders(self):
        self.log("Fetching open orders to cancel all...", category="Info")
        self._run_worker(
            self.client.orders.get_all_orders,
            self._cancel_all_open,
            lambda err: self.log(f"Failed to fetch orders: {err}", category="Error", error=True)
        )

    def _cancel_all_open(self, orders):
        open_statuses = ['OPEN', 'TRIGGER PENDING', 'PENDING', 'AMO REQ RECEIVED']
        open_orders = [o for o in orders if o.get('status') in open_statuses]
        if not open_orders:
            self.log("No open orders to cancel.", category="Warning")
            QMessageBox.information(self, "No Open Orders", "There are no pending orders.")
            return
        count = len(open_orders)
        self.log(f"Cancelling {count} open order(s)...", category="Info")
        for order in open_orders:
            order_id = order['order_id']
            variety = order.get('variety', 'regular')
            symbol = order.get('tradingsymbol', '')
            self._run_worker(
                self.client.orders.cancel_order,
                lambda res, oid=order_id, sym=symbol: self._cancel_result(res, oid, sym),
                lambda err, oid=order_id: self.log(f"Cancel {oid} failed: {err}", category="Error", error=True),
                order_id, variety
            )

    def _cancel_result(self, result, order_id, symbol):
        if result.get('status') == 'success':
            self.log(f"✅ Cancelled order {symbol} ({order_id})", category="Success")
        else:
            self.log(f"❌ Failed to cancel {order_id}: {result.get('message', 'Unknown error')}", category="Error", error=True)


# ========== Main Dashboard ==========
class ZerodhaDashboard(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zerodha Trading Dashboard")
        self.setGeometry(100, 100, 1300, 800)

        self.client = ZerodhaClient()
        self.log_entries = []
        self.log_filters = {
            'Error': True,
            'Info': True,
            'Warning': True,
            'Success': True
        }

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ========== FIRST CREATE LOG CONTAINER (so self.log_text exists) ==========
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.log_container = QWidget()
        self.log_container.setObjectName("log_container")
        self.log_container.setFixedWidth(int(self.width() * 0.2))
        log_layout = QVBoxLayout(self.log_container)
        log_layout.setContentsMargins(5, 5, 5, 5)

        # Filter checkboxes
        filter_layout = QHBoxLayout()
        self.chk_error = QCheckBox("Error")
        self.chk_info = QCheckBox("Info")
        self.chk_warning = QCheckBox("Warning")
        self.chk_success = QCheckBox("Success")
        self.chk_error.setChecked(True)
        self.chk_info.setChecked(True)
        self.chk_warning.setChecked(True)
        self.chk_success.setChecked(True)
        self.chk_error.stateChanged.connect(self.apply_log_filter)
        self.chk_info.stateChanged.connect(self.apply_log_filter)
        self.chk_warning.stateChanged.connect(self.apply_log_filter)
        self.chk_success.stateChanged.connect(self.apply_log_filter)
        filter_layout.addWidget(self.chk_error)
        filter_layout.addWidget(self.chk_info)
        filter_layout.addWidget(self.chk_warning)
        filter_layout.addWidget(self.chk_success)
        filter_layout.addStretch()
        log_layout.addLayout(filter_layout)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: monospace; font-size: 10pt; background-color: #1e1e1e; color: #d4d4d4;")
        log_layout.addWidget(self.log_text)

        right_layout.addWidget(self.log_container)
        right_layout.addStretch()

        # ========== NOW CREATE TABS (after log_text exists) ==========
        self.tabs = QTabWidget()
        self.holdings_tab = HoldingsTab(self.client, self.add_log_entry)
        self.positions_tab = PositionsTab(self.client, self.add_log_entry)
        self.open_orders_tab = OpenOrdersTab(self.client, self.add_log_entry)
        self.funds_tab = FundsTab(self.client, self.add_log_entry)
        self.order_tab = OrderPlacementTab(self.client, self.add_log_entry)

        self.tabs.addTab(self.holdings_tab, "Holdings")
        self.tabs.addTab(self.positions_tab, "Positions")
        self.tabs.addTab(self.open_orders_tab, "Open Orders")
        self.tabs.addTab(self.funds_tab, "Funds")
        self.tabs.addTab(self.order_tab, "Place Order")

        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Add to main layout
        main_layout.addWidget(self.tabs, 4)          # 80% width
        main_layout.addLayout(right_layout, 1)       # 20% width

        # Set default active tab to Place Order (index 4)
        self.tabs.setCurrentIndex(4)

        self.add_log_entry("Dashboard initialized. Ready.", category="Info")
        self.statusBar().showMessage("Ready")
    def resizeEvent(self, event):
        """Keep log container square (width = height) and place at top-right."""
        size = self.width()
        if hasattr(self, 'log_container'):
            width = int(size * 0.2)
            self.log_container.setFixedWidth(width)
            self.log_container.setFixedHeight(width)   # square
        super().resizeEvent(event)

    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        if tab_name == "Holdings":
            self.holdings_tab.refresh_data()
        elif tab_name == "Positions":
            self.positions_tab.refresh_data()
        elif tab_name == "Open Orders":
            self.open_orders_tab.refresh_data()
        elif tab_name == "Funds":
            self.funds_tab.refresh_data()
        # "Place Order" tab does not auto-refresh

    def add_log_entry(self, message, category="Info", error=False):
        if error and category == "Info":
            category = "Error"
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_entries.append((timestamp, message, category))
        self.apply_log_filter()

    def apply_log_filter(self):
        self.log_text.clear()
        for timestamp, message, category in self.log_entries:
            show = False
            if category == "Error" and self.chk_error.isChecked():
                show = True
            elif category == "Info" and self.chk_info.isChecked():
                show = True
            elif category == "Warning" and self.chk_warning.isChecked():
                show = True
            elif category == "Success" and self.chk_success.isChecked():
                show = True
            if show:
                color_map = {
                    "Error": "#ff6b6b",
                    "Info": "#e0e0e0",
                    "Warning": "#ffa500",
                    "Success": "#4ecdc4"
                }
                color = color_map.get(category, "#e0e0e0")
                prefix = ""
                if category == "Error":
                    prefix = "❌ "
                elif category == "Success":
                    prefix = "✓ "
                elif category == "Warning":
                    prefix = "⚠️ "
                else:
                    prefix = "ℹ️ "
                formatted = f'<span style="color:{color};">[{timestamp}] {prefix}{message}</span>'
                self.log_text.append(formatted)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ZerodhaDashboard()
    window.show()
    sys.exit(app.exec())