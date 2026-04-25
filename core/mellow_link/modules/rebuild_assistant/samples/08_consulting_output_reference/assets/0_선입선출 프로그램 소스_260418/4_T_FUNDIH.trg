---------- 4. T_FUNDIH
CREATE OR REPLACE
TRIGGER T_FUNDIH -- 입출금 내역을 수신하여 ERP 거래내역에 연동 (P_FUNDIH)
AFTER INSERT OR UPDATE OR DELETE ON HCMS_ACCT_TRSC_PTCL
FOR EACH ROW
DECLARE
   job varchar2(01);
BEGIN
   if INSERTING then
      job := 'A';
      P_FUNDIH(job
              ,:new.cnsv_cur_cd||:new.cryp_cnsv_acct_no ,:new.trsc_dt               ,:new.cnsv_acct_trsc_seq_no ,:new.trsc_drtm ,
              ,''               ,:new.rcv_wdrw_dv_cd    ,:new.tx_amt                ,:new.trsc_af_acct_bal      ,
              ,''               ,:new.cnsv_trsc_br_nm   ,:new.cnsv_acct_trsc_dv_ctt ,:new.rcrd_mttr_ctt         ,
              ,''               ,''                     ,''                         ,:new.inst_dv_no            ,
              ,ft_gncode('bank_code',:new.inst_dv_no)   ,:new.cryp_cnsv_acct_no     ,:new.cnsv_cur_cd           ,''             ,
              ,''               ,:new.indate            ,:new.intime );

   elsif UPDATING then
      job := 'U';
      P_FUNDIH(job
              ,:new.cnsv_cur_cd||:new.cryp_cnsv_acct_no ,:new.trsc_dt               ,:new.cnsv_acct_trsc_seq_no ,:new.trsc_drtm ,
              ,''               ,:new.rcv_wdrw_dv_cd    ,:new.tx_amt                ,:new.trsc_af_acct_bal      ,
              ,''               ,:new.cnsv_trsc_br_nm   ,:new.cnsv_acct_trsc_dv_ctt ,:new.rcrd_mttr_ctt         ,
              ,''               ,''                     ,''                         ,:new.inst_dv_no            ,
              ,ft_gncode('bank_code',:new.inst_dv_no)   ,:new.cryp_cnsv_acct_no     ,:new.cnsv_cur_cd           ,''             ,
              ,''               ,:new.indate            ,:new.intime );

   elsif DELETING then
      job := 'D';
      P_FUNDIH(job
              ,:old.cnsv_cur_cd||:old.cryp_cnsv_acct_no ,:old.trsc_dt               ,:old.cnsv_acct_trsc_seq_no ,:old.trsc_drtm ,
              ,''               ,:old.rcv_wdrw_dv_cd    ,:old.tx_amt                ,:old.trsc_af_acct_bal      ,
              ,''               ,:old.cnsv_trsc_br_nm   ,:old.cnsv_acct_trsc_dv_ctt ,:old.rcrd_mttr_ctt         ,
              ,''               ,''                     ,''                         ,:old.inst_dv_no            ,
              ,ft_gncode('bank_code',:old.inst_dv_no)   ,:old.cryp_cnsv_acct_no     ,:old.cnsv_cur_cd           ,''             ,
              ,''               ,:old.indate            ,:old.intime ); 
   end if;
END;