# Deterministic App Store screenshot compositor.
# Places each raw iOS screenshot into an IDENTICAL iPhone frame + caption
# layout on a 1290x2796 canvas so every frame is pixel-consistent (unlike
# per-image AI generation). Missing raws render as labeled placeholders.
param(
  [string]$InputDir  = "$env:USERPROFILE\Downloads\raw_screenshots",
  [string]$OutputDir = "$env:USERPROFILE\Downloads\AppStore_Screenshots_Deterministic"
)
Add-Type -AssemblyName System.Drawing

$W=1290; $H=2796; $bezel=22; $bodyTop=660; $bodyH=1896
$screenAspect = 1179.0/2556.0
$screenH = $bodyH-2*$bezel
$screenW = [int][math]::Round($screenH*$screenAspect)
$bodyW = $screenW+2*$bezel
$bodyX = [int](($W-$bodyW)/2)
$screenX = $bodyX+$bezel; $screenY = $bodyTop+$bezel
$radOuter=120; $radInner=96

$colTop=[Drawing.Color]::FromArgb(11,15,25)
$colBottom=[Drawing.Color]::FromArgb(22,33,62)
$colGray=[Drawing.Color]::FromArgb(156,163,175)
$colDisc=[Drawing.Color]::FromArgb(115,255,255,255)
$colBody=[Drawing.Color]::FromArgb(8,8,10)

$frames=@(
  @{file="01_leaderboard.png"; cap="The best AI and human traders."; sub="Every trade tracked the moment it's made."; disc="For educational purposes only. All trades on the platform are virtual using real market data."},
  @{file="02_alerts.png"; cap="Real-time alerts. Every move."; sub="Push notifications when traders trade."; disc=""},
  @{file="03_tracked.png"; cap="Tracked vs. S&P 500."; sub="Every period. Every portfolio. No spin."; disc=""},
  @{file="04_filter.png"; cap="Filter by sector or cap."; sub="Find traders who match your interest."; disc=""},
  @{file="05_scale.png"; cap="Scale any portfolio."; sub="Adjust to fit your size. Frozen at apply."; disc=""},
  @{file="06_earnings.png"; cap="Traders keep 85%*"; sub="The highest creator share in the industry."; disc="*See terms and conditions."}
)

function New-RoundedPath([int]$x,[int]$y,[int]$w,[int]$h,[int]$r){
  $p=New-Object Drawing.Drawing2D.GraphicsPath; $d=$r*2
  $p.AddArc($x,$y,$d,$d,180,90)
  $p.AddArc($x+$w-$d,$y,$d,$d,270,90)
  $p.AddArc($x+$w-$d,$y+$h-$d,$d,$d,0,90)
  $p.AddArc($x,$y+$h-$d,$d,$d,90,90)
  $p.CloseFigure(); return $p
}
function Get-WrappedLines($g,$text,$font,$maxW){
  $lines=New-Object System.Collections.ArrayList
  if([string]::IsNullOrWhiteSpace($text)){return $lines}
  $cur=""
  foreach($word in ($text -split ' ')){
    $try= if($cur -eq ""){$word}else{"$cur $word"}
    if($g.MeasureString($try,$font).Width -le $maxW){$cur=$try}
    else{ if($cur -ne ""){[void]$lines.Add($cur)}; $cur=$word }
  }
  if($cur -ne ""){[void]$lines.Add($cur)}
  return $lines
}
function Draw-CenteredLines($g,$lines,$font,$brush,[single]$startY,[single]$lineH){
  $y=$startY
  foreach($ln in $lines){
    $wsz=$g.MeasureString($ln,$font); $x=($W-$wsz.Width)/2
    $g.DrawString($ln,$font,$brush,$x,$y); $y+=$lineH
  }
  return $y
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Force -Path $InputDir  | Out-Null

$capFont=New-Object Drawing.Font("Segoe UI",92,[Drawing.FontStyle]::Bold,[Drawing.GraphicsUnit]::Pixel)
$subFont=New-Object Drawing.Font("Segoe UI",44,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
$discFont=New-Object Drawing.Font("Segoe UI",25,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
$phFont=New-Object Drawing.Font("Segoe UI",40,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
$whiteBrush=New-Object Drawing.SolidBrush([Drawing.Color]::White)
$grayBrush=New-Object Drawing.SolidBrush($colGray)
$discBrush=New-Object Drawing.SolidBrush($colDisc)
$bodyBrush=New-Object Drawing.SolidBrush($colBody)
$screenBgBrush=New-Object Drawing.SolidBrush([Drawing.Color]::Black)
$shadowBrush=New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(90,0,0,0))
$phBrush=New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(30,34,44))
$phTextBrush=New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(120,130,150))

foreach($f in $frames){
  $bmp=New-Object Drawing.Bitmap($W,$H)
  $g=[Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode=[Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.PixelOffsetMode=[Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.TextRenderingHint=[Drawing.Text.TextRenderingHint]::AntiAlias

  $rect=New-Object Drawing.Rectangle(0,0,$W,$H)
  $grad=New-Object Drawing.Drawing2D.LinearGradientBrush($rect,$colTop,$colBottom,[single]90)
  $g.FillRectangle($grad,$rect)

  $shPath=New-RoundedPath ($bodyX+6) ($bodyTop+22) $bodyW $bodyH $radOuter
  $g.FillPath($shadowBrush,$shPath)
  $bodyPath=New-RoundedPath $bodyX $bodyTop $bodyW $bodyH $radOuter
  $g.FillPath($bodyBrush,$bodyPath)

  $screenPath=New-RoundedPath $screenX $screenY $screenW $screenH $radInner
  $g.SetClip($screenPath)
  $g.FillRectangle($screenBgBrush,$screenX,$screenY,$screenW,$screenH)
  $path=Join-Path $InputDir $f.file
  if(Test-Path $path){
    $img=[Drawing.Image]::FromFile($path)
    $ratio=[math]::Min($screenW/$img.Width,$screenH/$img.Height)
    $dw=[int]($img.Width*$ratio); $dh=[int]($img.Height*$ratio)
    $dx=$screenX+[int](($screenW-$dw)/2); $dy=$screenY+[int](($screenH-$dh)/2)
    $g.DrawImage($img,$dx,$dy,$dw,$dh); $img.Dispose()
  } else {
    $g.FillRectangle($phBrush,$screenX,$screenY,$screenW,$screenH)
    $sf=New-Object Drawing.StringFormat
    $sf.Alignment=[Drawing.StringAlignment]::Center
    $sf.LineAlignment=[Drawing.StringAlignment]::Center
    $r2=New-Object Drawing.RectangleF($screenX,$screenY,$screenW,$screenH)
    $g.DrawString("[ drop $($f.file) here ]",$phFont,$phTextBrush,$r2,$sf)
  }
  $g.ResetClip()

  $capLines=Get-WrappedLines $g $f.cap $capFont 1130
  $subLines=Get-WrappedLines $g $f.sub $subFont 1130
  $capLH=$capFont.GetHeight($g)*1.05
  $subLH=$subFont.GetHeight($g)*1.2
  $gap=26
  $blockH=($capLines.Count*$capLH)+$gap+($subLines.Count*$subLH)
  $blockTop=$bodyTop-44-$blockH
  if($blockTop -lt 70){$blockTop=70}
  $afterCap=Draw-CenteredLines $g $capLines $capFont $whiteBrush $blockTop $capLH
  Draw-CenteredLines $g $subLines $subFont $grayBrush ($afterCap+$gap) $subLH | Out-Null

  if(-not [string]::IsNullOrWhiteSpace($f.disc)){
    $discLines=Get-WrappedLines $g $f.disc $discFont 1130
    $discLH=$discFont.GetHeight($g)*1.25
    $discStart=$H-60-($discLines.Count*$discLH)
    Draw-CenteredLines $g $discLines $discFont $discBrush $discStart $discLH | Out-Null
  }

  $out=Join-Path $OutputDir $f.file
  $bmp.Save($out,[Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Write-Host ("Wrote {0}" -f $f.file)
}
Write-Host "Done -> $OutputDir"
