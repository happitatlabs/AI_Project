CREATE OR REPLACE PROCEDURE P_FOROUT (
    p_flag VARCHAR2,
    p_bank_cd VARCHAR2,
    p_acnt_no VARCHAR2,
    p_tr_date VARCHAR2,
    p_tr_date_seq NUMBER,
    p_acct_seq VARCHAR2
) IS
BEGIN
    IF p_flag = 'A' THEN
        FOR src IN (
            SELECT ACCT_SEQ, TR_DATE, TR_DATE_SEQ, RMN_FAMT, RMN_AMT, EXCH_RATE
            FROM TN_FORINS
            WHERE ACCT_SEQ = p_acct_seq
            ORDER BY TR_DATE, TR_DATE_SEQ
        ) LOOP
            INSERT INTO TN_FOROUD (
                BANK_CD, ACNT_NO, OUT_DATE, OUT_DATE_SEQ, IN_DATE, IN_DATE_SEQ,
                OUTF_AMT, OUT_AMT0, GAP_AMT, MNEY_UNIT
            ) VALUES (
                p_bank_cd, p_acnt_no, p_tr_date, p_tr_date_seq, src.TR_DATE, src.TR_DATE_SEQ,
                src.RMN_FAMT, src.RMN_AMT, (src.RMN_AMT - src.RMN_FAMT * src.EXCH_RATE), 'USD'
            );
        END LOOP;

        INSERT INTO TN_BKCHIT (
            CHK, AC_DATE, AC_CHITNO, OCCR_PART, MNEY_UNIT, CHIT_AMT, TR_DATE, TR_DATE_SEQ
        ) VALUES (
            'CHK-FOROUT', p_tr_date, 'JE-OUT', 'exchange p/l', 'USD', 100, p_tr_date, p_tr_date_seq
        );
    ELSIF p_flag = 'D' THEN
        DELETE FROM TN_FOROUD
        WHERE BANK_CD = p_bank_cd
          AND ACNT_NO = p_acnt_no
          AND OUT_DATE = p_tr_date
          AND OUT_DATE_SEQ = p_tr_date_seq;
    END IF;
END P_FOROUT;
