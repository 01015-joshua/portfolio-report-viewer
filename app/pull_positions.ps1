param([Parameter(Mandatory=$true)][string]$JobFile,[Parameter(Mandatory=$true)][string]$OutputDir)
$ErrorActionPreference='Stop'
$roots=@('C:/blp','C:/Program Files/Bloomberg/blp','C:/Program Files (x86)/Bloomberg/blp')
$dllPath=$null
foreach($root in $roots){
 $candidate=Join-Path $root 'API/Office Tools/Bloomberglp.Blpapi.dll'
 if(Test-Path -LiteralPath $candidate -PathType Leaf){
  $dllPath=$candidate
  $searchPaths=@((Split-Path -Parent $candidate),(Join-Path $root 'DAPI'),$root)
  $env:PATH=($searchPaths -join ';')+';'+$env:PATH
  break
 }
}
if(!$dllPath){throw 'BLPAPI_DLL_NOT_FOUND'}
try {Add-Type -Path $dllPath} catch {throw 'BLPAPI_DLL_LOAD_FAILED'}
$job=Get-Content -LiteralPath $JobFile -Raw -Encoding UTF8 | ConvertFrom-Json
try {$session=[Bloomberglp.Blpapi.Session]::new()} catch {throw 'BLPAPI_DLL_LOAD_FAILED'}
try {
 if(!$session.Start()){throw 'BLPAPI_SESSION_UNAVAILABLE'}
 if(!$session.OpenService('//blp/refdata')){throw 'BLPAPI_SERVICE_UNAVAILABLE'}
 $service=$session.GetService('//blp/refdata')
 $queue=[System.Collections.Generic.Queue[string]]::new()
 foreach($day in $job.dates){$queue.Enqueue([string]$day)}
 $pending=@{}
 while($queue.Count -gt 0 -or $pending.Count -gt 0){
  while($queue.Count -gt 0 -and $pending.Count -lt 4){
   $day=$queue.Dequeue();$key=[long]$day
   $request=$service.CreateRequest('PortfolioDataRequest')
   $request.Append('securities',[string]$job.portfolio)
   $request.Append('fields','PORTFOLIO_DATA')
   $override=$request.GetElement('overrides').AppendElement()
   $override.SetElement('fieldId','REFERENCE_DATE');$override.SetElement('value',$day)
   $pending[$key]=@{date=$day;started=[datetime]::UtcNow;parts=[System.Collections.Generic.List[string]]::new()}
   $null=$session.SendRequest($request,[Bloomberglp.Blpapi.CorrelationID]::new($key))
  }
  $event=$session.NextEvent(500)
  if($event.Type.ToString() -in @('RESPONSE','PARTIAL_RESPONSE','REQUEST_STATUS')){
   foreach($message in $event){
    $key=[long]$message.CorrelationID.Value
    if(!$pending.ContainsKey($key)){continue}
    $p=$pending[$key];$p.parts.Add($message.ToString())
    if($event.Type.ToString() -eq 'REQUEST_STATUS'){throw 'Bloomberg request failed'}
    if($event.Type.ToString() -eq 'RESPONSE'){
     $body=$p.parts -join "`n"
     if($body -match '(?i)responseError|securityError|fieldException =|NOT_ENTITLED|NO_AUTH|DAILY_CAPACITY|request is blocked'){throw 'Bloomberg returned an entitlement, capacity, or data error'}
     [IO.File]::WriteAllText((Join-Path $OutputDir ($p.date+'.txt')),$body,[Text.UTF8Encoding]::new($false))
     $pending.Remove($key)
    }
   }
  }
  foreach($p in $pending.Values){if(([datetime]::UtcNow-$p.started).TotalSeconds -gt 40){throw 'Bloomberg request timeout'}}
 }
} finally {$session.Stop()}
