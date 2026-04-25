CREATE OR REPLACE
procedure p_FUNDIH -------- FNDIOX에 기록
(
   job            in varchar2,
   jacct_seq      in varchar2, -- 계좌일련번호
   jtr_date       in varchar2, -- 거래일자
   jtr_date_seq   in   number, -- 거래일자별일련번호
   jtr_time       in varchar2, -- 거래시간
   jtr_af_date    in varchar2, -- 후송거래일자
   jtr_ipji_gbn   in varchar2, -- 입출금거래구분
   jtr_amt        in   number, -- 거래금액
   jtr_af_amt     in   number, -- 거래후잔액
   jbr_cd         in varchar2, -- 거래점코드
   jbr_nm         in varchar2, -- 거래점명
   jjukyo         in varchar2, -- 적요
   jnaeyong       in varchar2, -- 내용
   jcms_nb        in varchar2, -- cms번호 (가상계좌번호)
   jco_reg_nb     in varchar2, -- 계좌주 사업자번호
   jco_nm         in varchar2, -- 계좌주 상호(이름)
   jbank_id       in varchar2, -- 은행코드
   jbank_nm       in varchar2, -- 은행명
   jacct_nb       in varchar2, -- 계좌번호
   jacct_tonghwa  in varchar2, -- 통화코드
   jacct_nm       in varchar2, -- 계좌명
   jacct_nick     in varchar2, -- 계좌별칭
   jacct_owner_nm in varchar2, -- 예금주명
   jlast_upd_date in varchar2, -- 마지막조회일자
   jlast_upd_time in varchar2  -- 마지막조회시간
   )
is
BEGIN 
   declare
      sysdt     varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
      systm     varchar2(06) := to_char(sysdate, 'hh24miss');
      wACNT_NO  varchar2(20) := jacct_nb;
      wcntt       number(12) := 0;
      werr_desc varchar2(2000);
   begin
      if job = 'A' then
         begin
            insert into ib_acctall_tr_dd_add/*fndiox*/ (
                        acct_seq    ,jtr_date     ,jtr_date_seq ,jtr_time     ,
                        tr_af_date  ,jtr_ipji_gbn ,jtr_amt      ,jtr_af_amt   ,
                        br_cd       ,br_nm        ,jukyo        ,naeyong      ,
                        cms_nb      ,co_reg_nb    ,co_nm        ,bank_id      ,
                        bank_nm     ,acct_nb      ,acct_tonghwa ,acct_nm      ,
                        acct_nick   ,acct_owner_nm,last_upd_date,last_upd_time,
                        acnt_unit_cd,
                        cnf_yn      ,cms_no       ,cust_cd      ,back_yn    )
                values (
                        jacct_seq   ,jtr_date      ,jtr_date_seq  ,nvl(jtr_time,systm) ,
                        jtr_af_date ,jtr_ipji_gbn  ,jtr_amt       ,jtr_af_amt  ,
                        jbr_cd      ,jbr_nm        ,jjukyo        ,jnaeyong    ,
                        jcms_nb     ,jco_reg_nb    ,jco_nm        ,jbank_id    ,
                        jbank_nm    ,wACNT_NO      ,jacct_tonghwa ,jacct_nm    , -- 다통화계좌
                        jacct_nick  ,jacct_owner_nm,jlast_upd_date,jlast_upd_time,
                        ft_acno_UNIT(wACNT_NO),
                        'N'         ,jcms_nb       ,ft_cms_custcd(jcms_nb), 'N' );
         exception when others then
                        werr_desc := '['||sqlcode||']'||sqlerrm;
                        begin
                           insert into ERRLOG(
                                       err_time, pgm_id, prc_yn, err_cn)
                               values (to_char(sysdate, 'yyyymmddhh24miss'), 'p_FUNDIH', 'N',
                                       rpad('거래내역 이관 오류 발생', 30, ' ')||
                                       rpad(jacct_seq, 20, ' ')||' '||jtr_date||'-'||rpad(to_char(jtr_date_seq), 5, ' ')||
                                       '!! 구분-'||jtr_ipji_gbn||' 금액-'||lpad(to_char(jtr_amt), 12, '0')||' 내용-'||rpad(jnaeyong, 30, ' ')||
                                       '!! 계좌-'||jacct_nb||' 통화-'||jacct_tonghwa||' 회계단위-'||ft_acno_UNIT(wACNT_NO)||werr_desc);
         end; 
      elsif job = 'U' then ---- 수정
         begin
            update ib_acctall_tr_dd_add/*fndiox*/ set
                   tr_time       = nvl(jtr_time, systm),
                   tr_af_date    = jtr_af_date,
                   tr_ipji_gbn   = jtr_ipji_gbn,
                   tr_amt        = jtr_amt,
                   tr_af_amt     = jtr_af_amt,
                   br_cd         = jbr_cd,
                   br_nm         = jbr_nm,
                   jukyo         = jjukyo,
                   naeyong       = jnaeyong,
                   cms_nb        = jcms_nb,
                   co_reg_nb     = jco_reg_nb,
                   co_nm         = jco_nm,
                   bank_id       = jbank_id,
                   bank_nm       = jbank_nm,
                   acnt_unit_cd  = nvl(acnt_unit_cd, ft_acno_unit(wACNT_NO)),
                   acct_nb       = wACNT_NO, -- 다통화계좌
                   acct_tonghwa  = jacct_tonghwa,
                   acct_nm       = jacct_nm,
                   acct_nick     = jacct_nick,
                   acct_owner_nm = jacct_owner_nm,
                   last_upd_date = jlast_upd_date,
                   last_upd_time = jlast_upd_time
            where bank_id      = jbank_id
              and acct_tonghwa = jacct_tonghwa
              and acct_nb      = wACNT_NO --- 다통화계좌
              and jtr_date     = jtr_date
              and jtr_date_seq = jtr_date_seq;
         end;
         if SQL%NOTFOUND then
            begin 
               insert into ib_acctall_tr_dd_add/*fndiox*/ (
                           acct_seq    ,jtr_date     ,jtr_date_seq ,jtr_time     ,
                           tr_af_date  ,jtr_ipji_gbn ,jtr_amt      ,jtr_af_amt   ,
                           br_cd       ,br_nm        ,jukyo        ,naeyong      ,
                           cms_nb      ,co_reg_nb    ,co_nm        ,bank_id      ,
                           bank_nm     ,acct_nb      ,acct_tonghwa ,acct_nm      ,
                           acct_nick   ,acct_owner_nm,last_upd_date,last_upd_time,
                           acnt_unit_cd,
                           cnf_yn      ,cms_no       ,cust_cd      ,back_yn    )
                   values (
                           jacct_seq   ,jtr_date      ,jtr_date_seq  ,nvl(jtr_time,systm) ,
                           jtr_af_date ,jtr_ipji_gbn  ,jtr_amt       ,jtr_af_amt  ,
                           jbr_cd      ,jbr_nm        ,jjukyo        ,jnaeyong    ,
                           jcms_nb     ,jco_reg_nb    ,jco_nm        ,jbank_id    ,
                           jbank_nm    ,wACNT_NO      ,jacct_tonghwa ,jacct_nm    , -- 다통화계좌
                           jacct_nick  ,jacct_owner_nm,jlast_upd_date,jlast_upd_time,
                           ft_acno_UNIT(wACNT_NO),
                           'N'         ,jcms_nb       ,ft_cms_custcd(jcms_nb), 'N' );
            end;
         end if;
      elsif job = 'D' then ---- 삭제 시
         begin
            delete ib_acctall_tr_dd_add/*fndiox*/
            where bank_id      = jbank_id
              and acct_tonghwa = jacct_tonghwa
              and acct_nb      = wACNT_NO
              and jtr_date     = jtr_date
              and jtr_date_seq = jtr_date_seq;
         end;
         if SQL%NOTFOUND then null;
         end if; 
      end if;
   end;
END p_FUNDIH;
