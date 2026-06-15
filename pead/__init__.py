"""Post-Earnings Announcement Drift (PEAD) backtester.

Detects earnings-gap events (Day-1 open >= +X% vs prior close) on a
universe of equities, simulates a long entry at Day-1 close with a
dynamic trailing stop, and reports cohort statistics.
"""
__version__ = "0.1.0"
