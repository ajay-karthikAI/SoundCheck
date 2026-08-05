SELECT
    (SELECT count(*) FROM fcst_.backtest_ledger) AS backtest_rows,
    (SELECT count(*) FROM fcst_.model_scores) AS model_score_rows,
    (SELECT count(*) FROM fcst_.predictions) AS prediction_rows,
    (SELECT count(*) FROM fcst_.next_up) AS next_up_rows;
