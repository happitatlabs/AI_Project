CREATE OR REPLACE PROCEDURE P_BKCHNO (
    p_chk VARCHAR2,
    p_ac_date VARCHAR2,
    p_ac_chitno VARCHAR2,
    p_occr_part VARCHAR2,
    p_mney_unit VARCHAR2
) IS
BEGIN
    INSERT INTO GL_INTERFACE (
        ACCOUNT_DATE, REFERENCE4, REFERENCE6, USER_JE_CATEGORY_NAME,
        CURRENCY_CODE, ENTERED_DR, ENTERED_CR
    ) VALUES (
        p_ac_date, p_chk, p_ac_chitno, 'deposit',
        p_mney_unit, 100, 100
    );
END P_BKCHNO;
