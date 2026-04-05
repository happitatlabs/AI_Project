<section class="legacy-report">
  <h1>Legacy Report Processing</h1>
  <script>
    const pendingQuery = "SELECT COUNT(*) FROM claim_adjustments WHERE claim_id = currentClaimId AND status = 'PENDING'";
    const directLoad = ReportRepository.count_pending_adjustments(currentClaimId);
  </script>
  <button id="submit-report">Submit</button>
  <button id="search-report">Search</button>
  <div id="validation-message"></div>
</section>
