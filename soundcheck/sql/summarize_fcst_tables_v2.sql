SELECT
    (SELECT count(*) FROM fcst_.backtest_ledger_v2) AS backtest_rows,
    (SELECT count(*) FROM fcst_.model_scores_v2) AS model_score_rows,
    (SELECT count(*) FROM fcst_.predictions_v2) AS prediction_rows;
