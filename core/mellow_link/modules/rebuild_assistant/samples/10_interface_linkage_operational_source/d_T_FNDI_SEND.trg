CREATE OR REPLACE TRIGGER T_FNDI_SEND
AFTER INSERT OR UPDATE OR DELETE ON IB_BULK_TRAN_ADD
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        IF :NEW.TRAN_STATUS = '02' THEN
            P_FUNDIH(
                'A',
                :NEW.FILE_DATE || :NEW.FILE_NUM || :NEW.FILE_SEQ,
                :NEW.TRAN_DT,
                :NEW.TRAN_DT_SEQ,
                :NEW.TRAN_IP_ACCT_NB,
                'KRW',
                :NEW.TRAN_AMT,
                :NEW.LAST_UPD_DATE,
                :NEW.LAST_UPD_TIME
            );
        END IF;
    ELSIF UPDATING THEN
        IF :NEW.TRAN_STATUS = '02' THEN
            P_FUNDIH(
                'U',
                :NEW.FILE_DATE || :NEW.FILE_NUM || :NEW.FILE_SEQ,
                :NEW.TRAN_DT,
                :NEW.TRAN_DT_SEQ,
                :NEW.TRAN_IP_ACCT_NB,
                'KRW',
                :NEW.TRAN_AMT,
                :NEW.LAST_UPD_DATE,
                :NEW.LAST_UPD_TIME
            );
        END IF;
    ELSIF DELETING THEN
        P_FUNDIH(
            'D',
            :OLD.FILE_DATE || :OLD.FILE_NUM || :OLD.FILE_SEQ,
            :OLD.TRAN_DT,
            :OLD.TRAN_DT_SEQ,
            :OLD.TRAN_IP_ACCT_NB,
            'KRW',
            :OLD.TRAN_AMT,
            :OLD.LAST_UPD_DATE,
            :OLD.LAST_UPD_TIME
        );
    END IF;
END;
