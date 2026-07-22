param(
  [string]$BackendUrl = $env:SMOKE_BACKEND_URL,
  [string]$FrontendUrl = $env:SMOKE_FRONTEND_URL,
  [string]$SummaryPath = $env:CORE_LOOP_SUMMARY_PATH,
  [switch]$StartDockerDeps,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not $BackendUrl) { $BackendUrl = "http://127.0.0.1:8003" }
if (-not $FrontendUrl) { $FrontendUrl = "http://localhost:3000" }
if (-not $SummaryPath) { $SummaryPath = Join-Path $repoRoot ".verify\core-loop-summary.json" }

$results = New-Object System.Collections.Generic.List[object]
$smokeHeaders = @{
  "x-user-id" = "00000000-0000-0000-0000-000000000000"
  "x-user-name" = "Core Loop Smoke"
  "x-client-type" = "desktop-smoke"
}

function Add-Check {
  param(
    [string]$Name,
    [bool]$Ok,
    [string]$Severity,
    [string]$Detail
  )
  $script:results.Add([pscustomobject]@{
    name = $Name
    ok = $Ok
    severity = $Severity
    detail = $Detail
  }) | Out-Null
}

function Test-TcpPort {
  param([string]$HostName, [int]$Port)
  try {
    $client = [System.Net.Sockets.TcpClient]::new()
    $async = $client.BeginConnect($HostName, $Port, $null, $null)
    $ready = $async.AsyncWaitHandle.WaitOne(1000)
    if (-not $ready) {
      $client.Close()
      return $false
    }
    $client.EndConnect($async)
    $client.Close()
    return $true
  } catch {
    return $false
  }
}

function Test-Http {
  param([string]$Uri)
  try {
    $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 15
    return @{ ok = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500); detail = "$($response.StatusCode) $($response.StatusDescription)" }
  } catch {
    return @{ ok = $false; detail = $_.Exception.Message }
  }
}

function Test-DockerEngine {
  try {
    $output = docker version --format "{{.Server.Version}}" 2>&1
    if ($LASTEXITCODE -eq 0 -and $output) {
      return @{ ok = $true; detail = "Docker engine $output" }
    }
    return @{ ok = $false; detail = [string]$output }
  } catch {
    return @{ ok = $false; detail = $_.Exception.Message }
  }
}

Write-Host "Arceus core loop verification" -ForegroundColor Cyan

$docker = Test-DockerEngine
Add-Check "Docker Desktop engine" $docker.ok "blocker" $docker.detail

if ($StartDockerDeps -and $docker.ok) {
  try {
    Push-Location $repoRoot
    docker compose up -d postgres redis | Out-Host
    Pop-Location
    Add-Check "Start docker dependencies" $true "ok" "docker compose up -d postgres redis"
  } catch {
    Pop-Location -ErrorAction SilentlyContinue
    Add-Check "Start docker dependencies" $false "blocker" $_.Exception.Message
  }
} elseif ($StartDockerDeps) {
  Add-Check "Start docker dependencies" $false "blocker" "Docker engine is unavailable. Start Docker Desktop first."
}

$postgresOk = Test-TcpPort "127.0.0.1" 5432
Add-Check "PostgreSQL reachable" $postgresOk "blocker" "127.0.0.1:5432"

$redisOk = Test-TcpPort "127.0.0.1" 6379
Add-Check "Redis reachable" $redisOk "warning" "127.0.0.1:6379"

$backendHealth = Test-Http "$BackendUrl/api/v1/health"
Add-Check "Agent backend health" $backendHealth.ok "blocker" "$BackendUrl/api/v1/health - $($backendHealth.detail)"

$backendReady = Test-Http "$BackendUrl/api/v1/ready"
Add-Check "Agent backend readiness" $backendReady.ok "blocker" "$BackendUrl/api/v1/ready - $($backendReady.detail)"

$frontendWorkspace = Test-Http "$FrontendUrl/workspace"
Add-Check "Frontend workspace route" $frontendWorkspace.ok "blocker" "$FrontendUrl/workspace - $($frontendWorkspace.detail)"

$downloadPage = Test-Http "$FrontendUrl/download"
Add-Check "Download route" $downloadPage.ok "warning" "$FrontendUrl/download - $($downloadPage.detail)"

$fixtureRepo = Join-Path $repoRoot "tests\fixtures\sample-repository"
$repositoryPayload = $null
if (Test-Path $fixtureRepo) {
  try {
    $body = @{
      workspace_id = "core-loop-fixture"
      root_path = $fixtureRepo
      force = $false
    } | ConvertTo-Json
    $response = Invoke-WebRequest -Uri "$BackendUrl/api/v1/repositories/analyze" -UseBasicParsing -Method POST -Body $body -ContentType "application/json" -TimeoutSec 20
    $payload = $response.Content | ConvertFrom-Json
    $repositoryPayload = $payload
    $ok = $response.StatusCode -ge 200 -and $response.StatusCode -lt 300 -and $payload.status -eq "completed" -and @($payload.frameworks).Count -gt 0
    Add-Check "Repository analysis endpoint" $ok "blocker" "$($payload.scanned_files) files; frameworks: $(@($payload.frameworks) -join ', '); summary: $($payload.summary)"
  } catch {
    Add-Check "Repository analysis endpoint" $false "blocker" $_.Exception.Message
  }
} else {
  Add-Check "Repository analysis fixture" $false "blocker" "$fixtureRepo is missing."
}

if ($repositoryPayload) {
  try {
    $missionBody = @{
      workspace_id = "core-loop-fixture"
      goal = "Implement Google OAuth login and verify it with tests"
      repository = @{
        repository_id = $repositoryPayload.repository_id
        root_path = $fixtureRepo
        summary = $repositoryPayload.summary
        languages = @($repositoryPayload.languages)
        frameworks = @($repositoryPayload.frameworks)
        package_managers = @($repositoryPayload.package_managers)
        entry_points = @($repositoryPayload.entry_points)
        services = @($repositoryPayload.services)
        test_commands = @($repositoryPayload.test_commands)
        database_usage = @($repositoryPayload.database_usage)
        authentication = @($repositoryPayload.authentication)
        architecture_style = $repositoryPayload.architecture_style
      }
    } | ConvertTo-Json -Depth 6
    $missionResponse = Invoke-WebRequest -Uri "$BackendUrl/api/v1/missions/compile-cognitive" -UseBasicParsing -Method POST -Body $missionBody -ContentType "application/json" -TimeoutSec 20
    $missionPayload = $missionResponse.Content | ConvertFrom-Json
    $missionOk = $missionResponse.StatusCode -ge 200 -and $missionResponse.StatusCode -lt 300 -and $missionPayload.state -eq "AWAITING_APPROVAL" -and @($missionPayload.tasks).Count -gt 0
    Add-Check "Cognitive mission compile" $missionOk "blocker" "$($missionPayload.understanding.intent)/$($missionPayload.understanding.domain); tasks: $(@($missionPayload.tasks).Count); confidence: $($missionPayload.report.confidence)"
  } catch {
    Add-Check "Cognitive mission compile" $false "blocker" $_.Exception.Message
  }
} else {
  Add-Check "Cognitive mission compile" $false "blocker" "Repository analysis payload unavailable."
}

if ($repositoryPayload) {
  try {
    $persistBody = @{
      workspace_id = "core-loop-fixture"
      goal = "Implement Google OAuth login and verify it with tests"
      repository = @{
        repository_id = $repositoryPayload.repository_id
        root_path = $fixtureRepo
        summary = $repositoryPayload.summary
        languages = @($repositoryPayload.languages)
        frameworks = @($repositoryPayload.frameworks)
        package_managers = @($repositoryPayload.package_managers)
        entry_points = @($repositoryPayload.entry_points)
        services = @($repositoryPayload.services)
        test_commands = @($repositoryPayload.test_commands)
        database_usage = @($repositoryPayload.database_usage)
        authentication = @($repositoryPayload.authentication)
        architecture_style = $repositoryPayload.architecture_style
      }
      constraints = @{
        verification = "core-loop"
      }
    } | ConvertTo-Json -Depth 8

    $missionKey = "core-loop-mission-$([guid]::NewGuid().ToString('N'))"
    $persistResponse = Invoke-WebRequest `
      -Uri "$BackendUrl/api/v1/missions/persisted" `
      -UseBasicParsing `
      -Method POST `
      -Headers ($smokeHeaders + @{ "Idempotency-Key" = $missionKey }) `
      -Body $persistBody `
      -ContentType "application/json" `
      -TimeoutSec 30
    $persistPayload = $persistResponse.Content | ConvertFrom-Json
    $persistOk = $persistResponse.StatusCode -ge 200 -and $persistResponse.StatusCode -lt 300 -and $persistPayload.display_status -eq "awaiting_approval" -and $persistPayload.approval_required -eq $true -and $persistPayload.task_count -gt 0
    Add-Check "Persisted mission create" $persistOk "blocker" "$($persistPayload.mission_id); status: $($persistPayload.display_status); planned tasks: $($persistPayload.task_count)"

    $readResponse = Invoke-WebRequest -Uri "$BackendUrl/api/v1/missions/persisted/$($persistPayload.mission_id)" -UseBasicParsing -Headers $smokeHeaders -TimeoutSec 20
    $readPayload = $readResponse.Content | ConvertFrom-Json
    $readOk = $readResponse.StatusCode -ge 200 -and $readResponse.StatusCode -lt 300 -and $readPayload.mission_id -eq $persistPayload.mission_id -and $readPayload.version -eq $persistPayload.version
    Add-Check "Persisted mission read" $readOk "blocker" "version $($readPayload.version); status: $($readPayload.display_status)"

    $approvalBody = @{
      expected_version = [int]$persistPayload.version
      approval_note = "Core loop verification approval."
    } | ConvertTo-Json
    $approvalKey = "core-loop-approval-$($persistPayload.mission_id)-$($persistPayload.version)"
    $approvalResponse = Invoke-WebRequest `
      -Uri "$BackendUrl/api/v1/missions/persisted/$($persistPayload.mission_id)/approve" `
      -UseBasicParsing `
      -Method POST `
      -Headers ($smokeHeaders + @{ "Idempotency-Key" = $approvalKey }) `
      -Body $approvalBody `
      -ContentType "application/json" `
      -TimeoutSec 30
    $approvalPayload = $approvalResponse.Content | ConvertFrom-Json
    $readyTasks = @($approvalPayload.tasks | Where-Object { $_.status -eq "ready" })
    $approvalOk = $approvalResponse.StatusCode -ge 200 -and $approvalResponse.StatusCode -lt 300 -and $approvalPayload.display_status -eq "queued" -and @($approvalPayload.tasks).Count -gt 0 -and $readyTasks.Count -gt 0
    Add-Check "Mission approval and queue" $approvalOk "blocker" "tasks: $(@($approvalPayload.tasks).Count); ready: $($readyTasks.Count); events: $(@($approvalPayload.events).Count)"

    if ($readyTasks.Count -gt 0) {
      $desktopSessionBody = @{
        device_id = "core-loop-device"
        workspace_id = "core-loop-fixture"
        repository_id = $repositoryPayload.repository_id
        capabilities = @{
          filesystem_read = $true
          filesystem_write = $true
          terminal = $true
          git = $true
          docker = $false
          network = $false
        }
        runtime = @{
          platform = "win32"
          architecture = "x64"
          app_version = "core-loop"
        }
      } | ConvertTo-Json -Depth 6
      $desktopSessionResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/desktop-sessions" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -Body $desktopSessionBody `
        -ContentType "application/json" `
        -TimeoutSec 20
      $desktopSessionPayload = $desktopSessionResponse.Content | ConvertFrom-Json
      $sessionOk = $desktopSessionResponse.StatusCode -ge 200 -and $desktopSessionResponse.StatusCode -lt 300 -and $desktopSessionPayload.status -eq "connected"
      Add-Check "Desktop session register" $sessionOk "blocker" "$($desktopSessionPayload.desktop_session_id); expires: $($desktopSessionPayload.expires_at)"

      $heartbeatBody = @{
        active_mission_id = $persistPayload.mission_id
        active_task_id = $null
        repository_available = $true
      } | ConvertTo-Json
      $heartbeatResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/desktop-sessions/$($desktopSessionPayload.desktop_session_id)/heartbeat" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -Body $heartbeatBody `
        -ContentType "application/json" `
        -TimeoutSec 20
      $heartbeatPayload = $heartbeatResponse.Content | ConvertFrom-Json
      $heartbeatOk = $heartbeatResponse.StatusCode -ge 200 -and $heartbeatResponse.StatusCode -lt 300 -and $heartbeatPayload.status -eq "connected"
      Add-Check "Desktop session heartbeat" $heartbeatOk "blocker" "$($heartbeatPayload.desktop_session_id); expires: $($heartbeatPayload.expires_at)"

      $rootTask = $readyTasks[0]
      $claimBody = @{
        desktop_session_id = $desktopSessionPayload.desktop_session_id
        expected_task_version = [int]$rootTask.version
        ttl_seconds = 90
      } | ConvertTo-Json
      $claimResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/missions/$($persistPayload.mission_id)/tasks/$($rootTask.id)/claim" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -Body $claimBody `
        -ContentType "application/json" `
        -TimeoutSec 20
      $claimPayload = $claimResponse.Content | ConvertFrom-Json
      $claimOk = $claimResponse.StatusCode -ge 200 -and $claimResponse.StatusCode -lt 300 -and $claimPayload.status -eq "claimed" -and $claimPayload.lease_token
      Add-Check "Desktop task claim" $claimOk "blocker" "$($rootTask.task_key); lease: $($claimPayload.lease_id)"

      $contextResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/missions/$($persistPayload.mission_id)/tasks/$($rootTask.id)/context" `
        -UseBasicParsing `
        -Method GET `
        -Headers ($smokeHeaders + @{ "X-Task-Lease-Token" = $claimPayload.lease_token }) `
        -TimeoutSec 20
      $contextPayload = $contextResponse.Content | ConvertFrom-Json
      $contextOk = $contextResponse.StatusCode -ge 200 -and $contextResponse.StatusCode -lt 300 -and $contextPayload.context_package_id -and @($contextPayload.permitted_tools).Count -gt 0
      Add-Check "Task context package" $contextOk "blocker" "tools: $(@($contextPayload.permitted_tools) -join ', '); paths: $(@($contextPayload.repository_context.relevant_paths).Count)"

      $controlledTaskJson = & node "$repoRoot\scripts\verify-desktop-controlled-task.js" --json
      if ($LASTEXITCODE -ne 0) {
        throw "Controlled desktop task execution failed."
      }
      $controlledTaskPayload = $controlledTaskJson | ConvertFrom-Json
      $controlledTaskOk = $controlledTaskPayload.ok -eq $true -and $controlledTaskPayload.change_set.review_state -eq "rolled_back" -and @($controlledTaskPayload.evidence).Count -ge 10
      Add-Check "Controlled desktop task execution" $controlledTaskOk "blocker" "evidence: $(@($controlledTaskPayload.evidence).Count); change-set: $($controlledTaskPayload.change_set.review_state)"

      $toolEvidenceBody = @{
        source = "desktop_tool_runtime"
        summary = "Desktop worker executed controlled fixture task using approved tools."
        records = @($controlledTaskPayload.evidence)
      } | ConvertTo-Json -Depth 8
      $toolEvidenceResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/missions/$($persistPayload.mission_id)/tasks/$($rootTask.id)/tool-evidence" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -Body $toolEvidenceBody `
        -ContentType "application/json" `
        -TimeoutSec 20
      $toolEvidencePayload = $toolEvidenceResponse.Content | ConvertFrom-Json
      $toolEvidenceOk = $toolEvidenceResponse.StatusCode -ge 200 -and $toolEvidenceResponse.StatusCode -lt 300 -and $toolEvidencePayload.data.evidence_count -ge 10
      Add-Check "Task tool evidence persistence" $toolEvidenceOk "blocker" "evidence: $($toolEvidencePayload.data.evidence_count)"

      $listedEvidenceResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/missions/$($persistPayload.mission_id)/evidence?task_id=$($rootTask.id)&evidence_type=tool_invocation" `
        -UseBasicParsing `
        -Headers $smokeHeaders `
        -TimeoutSec 20
      $listedEvidencePayload = $listedEvidenceResponse.Content | ConvertFrom-Json
      $listedEvidenceCount = @($listedEvidencePayload.data.items).Count
      if ($listedEvidenceCount -eq 0) {
        $listedEvidenceCount = @($listedEvidencePayload.data).Count
      }
      $listedEvidenceOk = $listedEvidenceResponse.StatusCode -ge 200 -and $listedEvidenceResponse.StatusCode -lt 300 -and $listedEvidenceCount -ge 10
      Add-Check "Task evidence retrieval" $listedEvidenceOk "blocker" "tool evidence rows: $listedEvidenceCount"

      $changeSetBody = @{
        title = $controlledTaskPayload.change_set.title
        summary = $controlledTaskPayload.change_set.summary
        review_state = $controlledTaskPayload.change_set.review_state
        source = $controlledTaskPayload.change_set.source
        changes = @($controlledTaskPayload.change_set.changes)
        metadata = @{
          repository_id = $repositoryPayload.repository_id
          desktop_session_id = $desktopSessionPayload.desktop_session_id
          controlled_task_repository = $controlledTaskPayload.disposable_repository
          evidence_count = @($controlledTaskPayload.evidence).Count
        }
      } | ConvertTo-Json -Depth 10
      $changeSetResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/missions/$($persistPayload.mission_id)/tasks/$($rootTask.id)/change-set" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -Body $changeSetBody `
        -ContentType "application/json" `
        -TimeoutSec 20
      $changeSetPayload = $changeSetResponse.Content | ConvertFrom-Json
      $changeSetOk = $changeSetResponse.StatusCode -ge 200 -and $changeSetResponse.StatusCode -lt 300 -and $changeSetPayload.data.review_state -eq "rolled_back" -and $changeSetPayload.data.artifact_id
      Add-Check "Task change-set artifact" $changeSetOk "blocker" "artifact: $($changeSetPayload.data.artifact_id); changes: $($changeSetPayload.data.change_count)"

      $renewBody = @{
        lease_token = $claimPayload.lease_token
        ttl_seconds = 90
      } | ConvertTo-Json
      $renewResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/missions/$($persistPayload.mission_id)/tasks/$($rootTask.id)/renew-lease" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -Body $renewBody `
        -ContentType "application/json" `
        -TimeoutSec 20
      $renewPayload = $renewResponse.Content | ConvertFrom-Json
      $renewOk = $renewResponse.StatusCode -ge 200 -and $renewResponse.StatusCode -lt 300 -and $renewPayload.lease_id -eq $claimPayload.lease_id
      Add-Check "Task lease renewal" $renewOk "blocker" "lease: $($renewPayload.lease_id); expires: $($renewPayload.lease_expires_at)"

      $doubleClaimBlocked = $false
      try {
        Invoke-WebRequest `
          -Uri "$BackendUrl/api/v1/missions/$($persistPayload.mission_id)/tasks/$($rootTask.id)/claim" `
          -UseBasicParsing `
          -Method POST `
          -Headers $smokeHeaders `
          -Body $claimBody `
          -ContentType "application/json" `
          -TimeoutSec 20 | Out-Null
      } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        $doubleClaimBlocked = $statusCode -eq 409
      }
      Add-Check "Task claim conflict protection" $doubleClaimBlocked "blocker" "Second claim must return 409 while lease is active."

      $completeBody = @{
        lease_token = $claimPayload.lease_token
        result = @{
          status = "completed"
          summary = "Repository context assembled by core-loop verification."
          files = @()
          changes = @()
          warnings = @()
          next_recommendations = @("Continue with architecture impact review.")
          evidence = @(
            @{
              kind = "context_package"
              context_package_id = $contextPayload.context_package_id
            }
          )
          metadata = @{
            verifier = "verify-core-loop"
          }
        }
      } | ConvertTo-Json -Depth 8
      $completeResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/missions/$($persistPayload.mission_id)/tasks/$($rootTask.id)/complete" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -Body $completeBody `
        -ContentType "application/json" `
        -TimeoutSec 20
      $completePayload = $completeResponse.Content | ConvertFrom-Json
      $completeOk = $completeResponse.StatusCode -ge 200 -and $completeResponse.StatusCode -lt 300 -and $completePayload.task_status -eq "completed" -and @($completePayload.released_tasks).Count -gt 0
      Add-Check "Task completion releases dependencies" $completeOk "blocker" "released: $(@($completePayload.released_tasks) -join ', '); mission: $($completePayload.mission_status)"

      $dispatchResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/task-runtime/missions/$($persistPayload.mission_id)/dispatch" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -TimeoutSec 20
      $dispatchPayload = $dispatchResponse.Content | ConvertFrom-Json
      $dispatchOk = $dispatchResponse.StatusCode -ge 200 -and $dispatchResponse.StatusCode -lt 300 -and $dispatchPayload.mission_status -in @("ready", "running", "completed")
      Add-Check "Task dispatcher poll" $dispatchOk "blocker" "ready: $(@($dispatchPayload.ready_tasks).Count); completed: $(@($dispatchPayload.completed_tasks).Count); mission: $($dispatchPayload.mission_status)"

      $scheduleResponse = Invoke-WebRequest `
        -Uri "$BackendUrl/api/v1/task-runtime/missions/$($persistPayload.mission_id)/schedule" `
        -UseBasicParsing `
        -Method POST `
        -Headers $smokeHeaders `
        -TimeoutSec 20
      $schedulePayload = $scheduleResponse.Content | ConvertFrom-Json
      $scheduleOk = $scheduleResponse.StatusCode -ge 200 -and $scheduleResponse.StatusCode -lt 300 -and @($schedulePayload.assignments).Count -ge 1 -and @($schedulePayload.agents).Count -ge 1
      Add-Check "Mission scheduler assignment" $scheduleOk "blocker" "assignments: $(@($schedulePayload.assignments).Count); agents: $(@($schedulePayload.agents).Count); waiting: $(@($schedulePayload.waiting_tasks).Count)"

      if ($scheduleOk) {
        $scheduledAssignment = @($schedulePayload.assignments)[0]
        $assignmentListResponse = Invoke-WebRequest `
          -Uri "$BackendUrl/api/v1/task-runtime/missions/$($persistPayload.mission_id)/assignments" `
          -UseBasicParsing `
          -Headers $smokeHeaders `
          -TimeoutSec 20
        $assignmentListPayload = $assignmentListResponse.Content | ConvertFrom-Json
        $persistedAssignmentOk = $assignmentListResponse.StatusCode -ge 200 -and $assignmentListResponse.StatusCode -lt 300 -and @($assignmentListPayload).Count -ge 1 -and @($assignmentListPayload | Where-Object { $_.id -eq $scheduledAssignment.assignment_id }).Count -eq 1
        Add-Check "Scheduler assignment persistence" $persistedAssignmentOk "blocker" "persisted assignments: $(@($assignmentListPayload).Count)"

        $duplicateScheduleResponse = Invoke-WebRequest `
          -Uri "$BackendUrl/api/v1/task-runtime/missions/$($persistPayload.mission_id)/schedule" `
          -UseBasicParsing `
          -Method POST `
          -Headers $smokeHeaders `
          -TimeoutSec 20
        $duplicateSchedulePayload = $duplicateScheduleResponse.Content | ConvertFrom-Json
        $duplicateAssignmentListResponse = Invoke-WebRequest `
          -Uri "$BackendUrl/api/v1/task-runtime/missions/$($persistPayload.mission_id)/assignments" `
          -UseBasicParsing `
          -Headers $smokeHeaders `
          -TimeoutSec 20
        $duplicateAssignmentListPayload = $duplicateAssignmentListResponse.Content | ConvertFrom-Json
        $idempotentScheduleOk = $duplicateScheduleResponse.StatusCode -ge 200 -and $duplicateScheduleResponse.StatusCode -lt 300 -and @($duplicateSchedulePayload.assignments).Count -eq 0 -and @($duplicateAssignmentListPayload).Count -eq @($assignmentListPayload).Count
        Add-Check "Scheduler idempotency" $idempotentScheduleOk "blocker" "new assignments: $(@($duplicateSchedulePayload.assignments).Count); total: $(@($duplicateAssignmentListPayload).Count)"

        $acceptBody = @{
          worker_id = $scheduledAssignment.agent_id
        } | ConvertTo-Json -Depth 5
        $acceptResponse = Invoke-WebRequest `
          -Uri "$BackendUrl/api/v1/task-runtime/assignments/$($scheduledAssignment.assignment_id)/accept" `
          -UseBasicParsing `
          -Method POST `
          -Headers $smokeHeaders `
          -Body $acceptBody `
          -ContentType "application/json" `
          -TimeoutSec 20
        $acceptPayload = $acceptResponse.Content | ConvertFrom-Json
        $acceptOk = $acceptResponse.StatusCode -ge 200 -and $acceptResponse.StatusCode -lt 300 -and $acceptPayload.status -eq "accepted"
        Add-Check "Scheduler assignment acceptance" $acceptOk "blocker" "assignment: $($acceptPayload.id); status: $($acceptPayload.status)"
      }
    } else {
      Add-Check "Desktop task claim" $false "blocker" "No ready task available after approval."
    }

    $graphResponse = Invoke-WebRequest -Uri "$BackendUrl/api/v1/missions/persisted/$($persistPayload.mission_id)/graph" -UseBasicParsing -Headers $smokeHeaders -TimeoutSec 20
    $graphPayload = $graphResponse.Content | ConvertFrom-Json
    $graphOk = $graphResponse.StatusCode -ge 200 -and $graphResponse.StatusCode -lt 300 -and @($graphPayload.nodes).Count -eq @($approvalPayload.tasks).Count -and @($graphPayload.edges).Count -gt 0
    Add-Check "Mission DAG graph" $graphOk "blocker" "nodes: $(@($graphPayload.nodes).Count); edges: $(@($graphPayload.edges).Count)"

    $repeatApprovalResponse = Invoke-WebRequest `
      -Uri "$BackendUrl/api/v1/missions/persisted/$($persistPayload.mission_id)/approve" `
      -UseBasicParsing `
      -Method POST `
      -Headers ($smokeHeaders + @{ "Idempotency-Key" = $approvalKey }) `
      -Body $approvalBody `
      -ContentType "application/json" `
      -TimeoutSec 30
    $repeatApprovalPayload = $repeatApprovalResponse.Content | ConvertFrom-Json
    $idempotentOk = $repeatApprovalResponse.StatusCode -ge 200 -and $repeatApprovalResponse.StatusCode -lt 300 -and @($repeatApprovalPayload.tasks).Count -eq @($approvalPayload.tasks).Count
    Add-Check "Mission approval idempotency" $idempotentOk "blocker" "task count stayed $(@($repeatApprovalPayload.tasks).Count)"

    $parallelSchedulerRaw = python scripts\verify-parallel-scheduler.py
    $parallelSchedulerPayload = $parallelSchedulerRaw | ConvertFrom-Json
    $parallelSchedulerOk = [bool]$parallelSchedulerPayload.ok
    $failedParallelChecks = @($parallelSchedulerPayload.checks | Where-Object { -not $_.ok })
    Add-Check "Parallel scheduler durable proof" $parallelSchedulerOk "blocker" "checks: $(@($parallelSchedulerPayload.checks).Count); failed: $(@($failedParallelChecks).Count)"

    $schedulerRecoveryRaw = python scripts\verify-scheduler-recovery.py
    $schedulerRecoveryPayload = $schedulerRecoveryRaw | ConvertFrom-Json
    $schedulerRecoveryOk = [bool]$schedulerRecoveryPayload.ok
    $failedRecoveryChecks = @($schedulerRecoveryPayload.checks | Where-Object { -not $_.ok })
    Add-Check "Scheduler crash recovery proof" $schedulerRecoveryOk "blocker" "checks: $(@($schedulerRecoveryPayload.checks).Count); failed: $(@($failedRecoveryChecks).Count)"

    $interruptedRecoveryRaw = node scripts\verify-interrupted-execution-recovery.js
    $interruptedRecoveryPayload = $interruptedRecoveryRaw | ConvertFrom-Json
    $interruptedRecoveryOk = [bool]$interruptedRecoveryPayload.ok
    $failedInterruptedChecks = @($interruptedRecoveryPayload.checks | Where-Object { -not $_.ok })
    Add-Check "Interrupted execution recovery proof" $interruptedRecoveryOk "blocker" "checks: $(@($interruptedRecoveryPayload.checks).Count); failed: $(@($failedInterruptedChecks).Count)"

    $missionObservabilityRaw = python scripts\verify-mission-observability.py
    $missionObservabilityPayload = $missionObservabilityRaw | ConvertFrom-Json
    $missionObservabilityOk = [bool]$missionObservabilityPayload.ok
    $failedObservabilityChecks = @($missionObservabilityPayload.checks | Where-Object { -not $_.ok })
    Add-Check "Mission observability proof" $missionObservabilityOk "blocker" "checks: $(@($missionObservabilityPayload.checks).Count); failed: $(@($failedObservabilityChecks).Count)"

    $workerCoordinatorRaw = node scripts\verify-worker-coordinator.js
    $workerCoordinatorPayload = $workerCoordinatorRaw | ConvertFrom-Json
    $workerCoordinatorOk = [bool]$workerCoordinatorPayload.ok
    Add-Check "Desktop worker coordinator proof" $workerCoordinatorOk "blocker" "accepted: $($workerCoordinatorPayload.accepted); claimed: $($workerCoordinatorPayload.claimed); completed: $($workerCoordinatorPayload.completed); heartbeats: $($workerCoordinatorPayload.heartbeats); overlap: $($workerCoordinatorPayload.overlap)"
  } catch {
    Add-Check "Persisted mission approval loop" $false "blocker" $_.Exception.Message
  }
} else {
  Add-Check "Persisted mission approval loop" $false "blocker" "Repository analysis payload unavailable."
}

$installer = Join-Path $repoRoot "desktop\dist\Arceus Code-1.0.0-Setup.exe"
if (Test-Path $installer) {
  $item = Get-Item $installer
  Add-Check "Desktop installer artifact" $true "ok" "$($item.FullName) ($([math]::Round($item.Length / 1MB, 1)) MB)"
} else {
  Add-Check "Desktop installer artifact" $false "warning" "Run: cd desktop; npm run dist:local"
}

$manualChecklist = @(
  "Open Folder",
  "File Explorer",
  "Open/Edit/Save file",
  "Dirty state indicator",
  "Terminal create/kill",
  "Layout persistence",
  "Download/install flow",
  "Desktop launch",
  "Workspace reload",
  "Offline mode",
  "Service reconnect"
)
Add-Check "Manual regression checklist" $true "ok" ($manualChecklist -join "; ")

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SummaryPath) | Out-Null
$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  backend_url = $BackendUrl
  frontend_url = $FrontendUrl
  checks = $results
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $SummaryPath -Encoding UTF8

$results | Format-Table name, ok, severity, detail -AutoSize
Write-Host "Summary written to $SummaryPath" -ForegroundColor DarkGray

$blockers = @($results | Where-Object { $_.severity -eq "blocker" -and -not $_.ok })
if ($blockers.Count -gt 0) {
  $message = "Core loop verification failed: $($blockers.Count) blocker(s)."
  if ($Strict) { throw $message }
  Write-Warning $message
  exit 1
}

Write-Host "Core loop verification passed." -ForegroundColor Green
