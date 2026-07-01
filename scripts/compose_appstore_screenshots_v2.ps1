# App Store screenshot compositor v2.
#
# TWO MODES
#   1) BASE-FRAME (recommended, premium look): drop ONE Gemini-generated empty
#      iPhone mockup named `frame.png` into -InputDir. It must be the device on
#      the navy gradient with the SCREEN filled a solid bright MAGENTA (#FF00FF)
#      and NO caption text. The script color-keys the magenta to transparent and
#      composites each real screenshot BEHIND the frame, so all 6 frames reuse
#      the exact same premium chrome with pixel-consistent captions.
#   2) DRAWN-FRAME (fallback): if frame.png is absent, a clean flat device frame
#      is drawn programmatically (with side buttons + soft shadow).
#
# FONTS: pass real fonts if you have them, else defaults to Segoe UI.
#   -CaptionFont C:\path\SF-Pro-Display-Bold.otf  -BodyFont C:\path\SF-Pro-Text-Regular.otf
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File compose_appstore_screenshots_v2.ps1
param(
  [string]$InputDir    = "$env:USERPROFILE\Downloads\raw_screenshots",
  [string]$OutputDir   = "$env:USERPROFILE\Downloads\AppStore_Screenshots_v2",
  [string]$FrameFile   = "",
  [string]$CaptionFont = "",
  [string]$BodyFont    = ""
)
Add-Type -AssemblyName System.Drawing

$W=1290; $H=2796
$colTop=[Drawing.Color]::FromArgb(11,15,25)
$colBottom=[Drawing.Color]::FromArgb(22,33,62)
$colGray=[Drawing.Color]::FromArgb(156,163,175)
$colDisc=[Drawing.Color]::FromArgb(115,255,255,255)

$frames=@(
  @{file="01_leaderboard.png"; cap="The best AI and human traders."; sub="Every trade tracked the moment it's made."; disc="For educational purposes only. All trades on the platform are virtual using real market data."},
  @{file="02_alerts.png"; cap="Real-time alerts. Every move."; sub="Push notifications when traders trade."; disc=""},
  @{file="03_tracked.png"; cap="Tracked vs. S&P 500."; sub="Every period. Every portfolio. No spin."; disc=""},
  @{file="04_filter.png"; cap="Filter by sector or cap."; sub="Find traders who match your interest."; disc=""},
  @{file="05_scale.png"; cap="Scale any portfolio."; sub="Adjust to fit your size. Frozen at apply."; disc=""},
  @{file="06_earnings.png"; cap="Traders keep 85%*"; sub="The highest creator share in the industry."; disc="*See terms and conditions."}
)

# ---------- fonts ----------
$script:pfc = New-Object Drawing.Text.PrivateFontCollection
function Get-Family([string]$path,[string]$fallback){
  if($path -and (Test-Path $path)){
    try { $script:pfc.AddFontFile($path); return $script:pfc.Families[-1] } catch { Write-Host "Font load failed ($path): $_" }
  }
  return (New-Object Drawing.FontFamily($fallback))
}
$capFamily  = Get-Family $CaptionFont "Segoe UI"
$bodyFamily = Get-Family $BodyFont    "Segoe UI"
# A custom OTF is usually already the desired weight -> render Regular; the
# built-in fallback needs an explicit Bold for the caption.
$capStyle = if($CaptionFont -and (Test-Path $CaptionFont)){[Drawing.FontStyle]::Regular}else{[Drawing.FontStyle]::Bold}
$capFont  = New-Object Drawing.Font($capFamily,74,$capStyle,[Drawing.GraphicsUnit]::Pixel)
$subFont  = New-Object Drawing.Font($bodyFamily,40,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
$discFont = New-Object Drawing.Font($bodyFamily,26,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
$phFont   = New-Object Drawing.Font($bodyFamily,40,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
$whiteBrush=New-Object Drawing.SolidBrush([Drawing.Color]::White)
$grayBrush =New-Object Drawing.SolidBrush($colGray)
$discBrush =New-Object Drawing.SolidBrush($colDisc)

# ---------- helpers ----------
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
function Draw-Header($g,$cap,$sub,[single]$deviceTop){
  $capLines=Get-WrappedLines $g $cap $capFont 1100
  $subLines=Get-WrappedLines $g $sub $subFont 1100
  $capLH=$capFont.GetHeight($g)*1.02
  $subLH=$subFont.GetHeight($g)*1.15
  $gap=16
  $blockH=($capLines.Count*$capLH)+$gap+($subLines.Count*$subLH)
  $blockTop=$deviceTop-56-$blockH
  if($blockTop -lt 60){$blockTop=60}
  $afterCap=Draw-CenteredLines $g $capLines $capFont $whiteBrush $blockTop $capLH
  Draw-CenteredLines $g $subLines $subFont $grayBrush ($afterCap+$gap) $subLH | Out-Null
}
function Draw-Disclaimer($g,$disc){
  if([string]::IsNullOrWhiteSpace($disc)){return}
  $lines=Get-WrappedLines $g $disc $discFont 1130
  $lh=$discFont.GetHeight($g)*1.25
  $start=$H-72-($lines.Count*$lh)
  Draw-CenteredLines $g $lines $discFont $discBrush $start $lh | Out-Null
}
function Fill-Gradient($g){
  $rect=New-Object Drawing.Rectangle(0,0,$W,$H)
  $grad=New-Object Drawing.Drawing2D.LinearGradientBrush($rect,$colTop,$colBottom,[single]90)
  $g.FillRectangle($grad,$rect)
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Force -Path $InputDir  | Out-Null

# ---------- base-frame detection (magenta screen -> transparent) ----------
if(-not $FrameFile){ $FrameFile = Join-Path $InputDir "frame.png" }
$baseFrame=$null; $bx=0;$by=0;$bw=0;$bh=0
if(Test-Path $FrameFile){
  $src=[Drawing.Image]::FromFile($FrameFile)
  $baseFrame=New-Object Drawing.Bitmap($W,$H)
  $gg=[Drawing.Graphics]::FromImage($baseFrame)
  $gg.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $gg.DrawImage($src,0,0,$W,$H); $gg.Dispose(); $src.Dispose()
  $bd=$baseFrame.LockBits((New-Object Drawing.Rectangle(0,0,$W,$H)),[Drawing.Imaging.ImageLockMode]::ReadOnly,[Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $stride=$bd.Stride
  $buf=New-Object byte[] ($stride*$H)
  [Runtime.InteropServices.Marshal]::Copy($bd.Scan0,$buf,0,$buf.Length)
  $baseFrame.UnlockBits($bd)
  $minX=$W;$minY=$H;$maxX=0;$maxY=0;$step=2
  for($y=0;$y -lt $H;$y+=$step){
    $row=$y*$stride
    for($x=0;$x -lt $W;$x+=$step){
      $i=$row+$x*4
      if($buf[$i+2] -gt 165 -and $buf[$i+1] -lt 105 -and $buf[$i] -gt 165){
        if($x -lt $minX){$minX=$x}; if($x -gt $maxX){$maxX=$x}
        if($y -lt $minY){$minY=$y}; if($y -gt $maxY){$maxY=$y}
      }
    }
  }
  if($maxX -gt $minX -and $maxY -gt $minY){
    $bx=$minX;$by=$minY;$bw=$maxX-$minX;$bh=$maxY-$minY
    Write-Host "Base frame in use. Detected screen region: x=$bx y=$by w=$bw h=$bh"
  } else {
    Write-Host "WARNING: no magenta screen found in $FrameFile (check the key color). Using drawn frame."
    $baseFrame.Dispose(); $baseFrame=$null
  }
}
$ia=New-Object Drawing.Imaging.ImageAttributes
$ia.SetColorKey([Drawing.Color]::FromArgb(140,0,140),[Drawing.Color]::FromArgb(255,130,255),[Drawing.Imaging.ColorAdjustType]::Default)

# ---------- drawn-frame geometry (fallback) ----------
$bezel=20; $fbTop=690; $fbH=1836
$fbScreenH=$fbH-2*$bezel
$fbScreenW=[int][math]::Round($fbScreenH*(1179.0/2556.0))
$fbW=$fbScreenW+2*$bezel
$fbX=[int](($W-$fbW)/2)
$fbScreenX=$fbX+$bezel; $fbScreenY=$fbTop+$bezel
$radOuter=140;$radInner=120

foreach($f in $frames){
  $bmp=New-Object Drawing.Bitmap($W,$H)
  $g=[Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode=[Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.PixelOffsetMode=[Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.TextRenderingHint=[Drawing.Text.TextRenderingHint]::AntiAlias

  Fill-Gradient $g
  $imgPath=Join-Path $InputDir $f.file
  $shot=$null
  if(Test-Path $imgPath){ $shot=[Drawing.Image]::FromFile($imgPath) }

  if($baseFrame){
    if($shot){
      $ratio=[math]::Max($bw/$shot.Width,$bh/$shot.Height)   # cover
      $dw=[int]($shot.Width*$ratio); $dh=[int]($shot.Height*$ratio)
      $dx=$bx+[int](($bw-$dw)/2); $dy=$by+[int](($bh-$dh)/2)
      $g.SetClip((New-Object Drawing.Rectangle($bx,$by,$bw,$bh)))
      $g.DrawImage($shot,$dx,$dy,$dw,$dh)
      $g.ResetClip()
    }
    $g.DrawImage($baseFrame,(New-Object Drawing.Rectangle(0,0,$W,$H)),0,0,$W,$H,[Drawing.GraphicsUnit]::Pixel,$ia)
    Draw-Header $g $f.cap $f.sub $by
  } else {
    for($s=12;$s -ge 2;$s-=5){
      $a=[int](60/$s)
      $sp=New-RoundedPath ($fbX-$s) ($fbTop-$s+16) ($fbW+2*$s) ($fbH+2*$s) ($radOuter+$s)
      $g.FillPath((New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb($a,0,0,0))),$sp)
    }
    $edge=New-RoundedPath ($fbX-3) ($fbTop-3) ($fbW+6) ($fbH+6) ($radOuter+3)
    $g.FillPath((New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(70,80,92))),$edge)
    $g.FillPath((New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(8,8,10))),(New-RoundedPath $fbX $fbTop $fbW $fbH $radOuter))
    $btn=New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(55,63,74))
    $g.FillRectangle($btn,($fbX-4),($fbTop+230),6,64)
    $g.FillRectangle($btn,($fbX-4),($fbTop+340),6,120)
    $g.FillRectangle($btn,($fbX-4),($fbTop+480),6,120)
    $g.FillRectangle($btn,($fbX+$fbW-2),($fbTop+360),6,180)
    $screen=New-RoundedPath $fbScreenX $fbScreenY $fbScreenW $fbScreenH $radInner
    $g.SetClip($screen)
    $g.FillRectangle((New-Object Drawing.SolidBrush([Drawing.Color]::Black)),$fbScreenX,$fbScreenY,$fbScreenW,$fbScreenH)
    if($shot){
      $ratio=[math]::Min($fbScreenW/$shot.Width,$fbScreenH/$shot.Height)
      $dw=[int]($shot.Width*$ratio); $dh=[int]($shot.Height*$ratio)
      $dx=$fbScreenX+[int](($fbScreenW-$dw)/2); $dy=$fbScreenY+[int](($fbScreenH-$dh)/2)
      $g.DrawImage($shot,$dx,$dy,$dw,$dh)
    } else {
      $sf=New-Object Drawing.StringFormat; $sf.Alignment=[Drawing.StringAlignment]::Center; $sf.LineAlignment=[Drawing.StringAlignment]::Center
      $g.DrawString("[ drop $($f.file) here ]",$phFont,(New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(120,130,150))),(New-Object Drawing.RectangleF($fbScreenX,$fbScreenY,$fbScreenW,$fbScreenH)),$sf)
    }
    $g.ResetClip()
    Draw-Header $g $f.cap $f.sub $fbTop
  }

  Draw-Disclaimer $g $f.disc
  if($shot){ $shot.Dispose() }
  $bmp.Save((Join-Path $OutputDir $f.file),[Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Write-Host ("Wrote {0}" -f $f.file)
}
if($baseFrame){$baseFrame.Dispose()}
Write-Host "Done -> $OutputDir"
