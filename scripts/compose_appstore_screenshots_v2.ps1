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
  [string]$BodyFont    = "",
  [int]$CaptionSize    = 90,    # headline px (large + bold reads well at thumbnail size)
  [int]$SubtitleSize   = 46,    # subtitle px (~half the headline for clear hierarchy)
  [int]$CaptionTop     = 150    # fixed Y for the headline's first line -> same on all 6
)
Add-Type -AssemblyName System.Drawing
# Compiled chroma-key: transparent where the pixel is magenta-dominant
# (green deficit = min(R,B)-G). Removes anti-aliased screen/notch edges that a
# rectangular color key leaves as a pink fringe, while keeping grays / titanium
# frame (R~=G~=B => deficit ~0). Also returns the SOLID magenta screen bbox.
Add-Type -TypeDefinition @"
using System;
public static class ChromaKey {
  public static int[] Apply(byte[] buf, int stride, int W, int H){
    int minX=W, minY=H, maxX=0, maxY=0;
    for(int y=0;y<H;y++){
      int row=y*stride;
      for(int x=0;x<W;x++){
        int i=row+x*4;
        int b=buf[i], g=buf[i+1], r=buf[i+2];
        int mn = r<b ? r : b;
        int deficit = mn-g;
        if(deficit>40 && r>60 && b>60){
          buf[i+3]=0;
          if(deficit>120 && r>150 && b>150){
            if(x<minX)minX=x; if(x>maxX)maxX=x;
            if(y<minY)minY=y; if(y>maxY)maxY=y;
          }
        }
      }
    }
    return new int[]{minX,minY,maxX,maxY};
  }
}
"@

$W=1290; $H=2796
$colTop=[Drawing.Color]::FromArgb(11,15,25)
$colBottom=[Drawing.Color]::FromArgb(22,33,62)
$colGray=[Drawing.Color]::FromArgb(156,163,175)
$colDisc=[Drawing.Color]::FromArgb(175,255,255,255)   # brighter so the fine-print stays legible

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
$capFont  = New-Object Drawing.Font($capFamily,$CaptionSize,$capStyle,[Drawing.GraphicsUnit]::Pixel)
$subFont  = New-Object Drawing.Font($bodyFamily,$SubtitleSize,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
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
function Get-BalancedLines($g,$text,$font,$maxW){
  # Headline wrapping: 1 line if it fits, else the 2-line split that minimizes the
  # widest line, with a bias toward breaking right after a sentence period so
  # e.g. "Real-time alerts. Every move." -> "Real-time alerts." / "Every move."
  $lines=New-Object System.Collections.ArrayList
  if([string]::IsNullOrWhiteSpace($text)){return $lines}
  $words=@($text -split ' ')
  if($words.Count -eq 1 -or $g.MeasureString($text,$font).Width -le $maxW){
    [void]$lines.Add($text); return $lines
  }
  $best=1; $bestCost=[double]::MaxValue
  for($k=1;$k -lt $words.Count;$k++){
    $l1=($words[0..($k-1)] -join ' '); $l2=($words[$k..($words.Count-1)] -join ' ')
    $cost=[Math]::Max($g.MeasureString($l1,$font).Width,$g.MeasureString($l2,$font).Width)
    if($words[$k-1].EndsWith('.') -or $words[$k-1].EndsWith(':')){ $cost -= 45 }
    if($cost -lt $bestCost){ $bestCost=$cost; $best=$k }
  }
  $l1=($words[0..($best-1)] -join ' '); $l2=($words[$best..($words.Count-1)] -join ' ')
  if(($g.MeasureString($l1,$font).Width -gt $maxW) -or ($g.MeasureString($l2,$font).Width -gt $maxW)){
    return (Get-WrappedLines $g $text $font $maxW)   # very long -> fall back to greedy (3+ lines)
  }
  [void]$lines.Add($l1); [void]$lines.Add($l2); return $lines
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
  # TOP-anchored at a fixed Y ($CaptionTop) so the headline sits at the SAME
  # position on all 6 screenshots -> a consistent, professional gallery. Only the
  # words change frame-to-frame; size / weight / placement stay identical.
  # Narrower caption wrap (980) encourages balanced 2-line breaks on long headlines.
  $capLines=Get-BalancedLines $g $cap $capFont 980
  $subLines=Get-WrappedLines $g $sub $subFont 1050
  $capLH=$capFont.GetHeight($g)*1.06
  $subLH=$subFont.GetHeight($g)*1.20
  $gap=[single]($capLH*0.30)
  $blockH=($capLines.Count*$capLH)+$gap+($subLines.Count*$subLH)
  $top=[single]$CaptionTop
  $maxTop=$deviceTop-48-$blockH            # never let the header touch the phone
  if($top -gt $maxTop){$top=[Math]::Max([single]48,$maxTop)}
  $afterCap=Draw-CenteredLines $g $capLines $capFont $whiteBrush $top $capLH
  Draw-CenteredLines $g $subLines $subFont $grayBrush ($afterCap+$gap) $subLH | Out-Null
}
function Draw-Disclaimer($g,$disc,[single]$deviceBottom){
  if([string]::IsNullOrWhiteSpace($disc)){return}
  $maxW=1130; $bottomMargin=56; $gapAbove=56   # gapAbove clears the phone's bottom bezel
  # Shrink-to-fit so the disclaimer always lands in the navy band BELOW the device.
  # Larger base size (32px) for legibility; balanced wrap avoids orphan words like "data."
  for($fs=32; $fs -ge 26; $fs--){
    $f=New-Object Drawing.Font($bodyFamily,$fs,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
    $lines=Get-BalancedLines $g $disc $f $maxW
    $lh=$f.GetHeight($g)*1.28
    $top=$H-$bottomMargin-($lines.Count*$lh)
    if($top -ge ($deviceBottom+$gapAbove)){
      Draw-CenteredLines $g $lines $f $discBrush $top $lh | Out-Null
      $f.Dispose(); return
    }
    $f.Dispose()
  }
  # Even at the smallest size it collides with the device -> draw just below it and warn.
  $f=New-Object Drawing.Font($bodyFamily,26,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
  $lines=Get-BalancedLines $g $disc $f $maxW
  $lh=$f.GetHeight($g)*1.28
  $short=[int]((($deviceBottom+$gapAbove)+($lines.Count*$lh)+$bottomMargin)-$H)
  Write-Host ("WARNING: disclaimer doesn't fit below the phone (short by ~$short px). Regenerate frame.png with the phone ~$short px higher (or slightly smaller) for clean spacing.")
  Draw-CenteredLines $g $lines $f $discBrush ($deviceBottom+$gapAbove) $lh | Out-Null
  $f.Dispose()
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
  $bd=$baseFrame.LockBits((New-Object Drawing.Rectangle(0,0,$W,$H)),[Drawing.Imaging.ImageLockMode]::ReadWrite,[Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $stride=$bd.Stride
  $buf=New-Object byte[] ($stride*$H)
  [Runtime.InteropServices.Marshal]::Copy($bd.Scan0,$buf,0,$buf.Length)
  $box=[ChromaKey]::Apply($buf,$stride,$W,$H)          # keys magenta -> transparent + finds screen bbox
  $minX=$box[0];$minY=$box[1];$maxX=$box[2];$maxY=$box[3]
  [Runtime.InteropServices.Marshal]::Copy($buf,0,$bd.Scan0,$buf.Length)
  $baseFrame.UnlockBits($bd)
  if($maxX -gt $minX -and $maxY -gt $minY){
    $bx=$minX;$by=$minY;$bw=$maxX-$minX;$bh=$maxY-$minY
    Write-Host "Base frame in use. Detected screen region: x=$bx y=$by w=$bw h=$bh"
  } else {
    Write-Host "WARNING: no magenta screen found in $FrameFile (check the key color). Using drawn frame."
    $baseFrame.Dispose(); $baseFrame=$null
  }
}
# (magenta removal is now baked into $baseFrame's alpha by the chroma pass above)

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
      $pad=8                                                 # bleed under the keyed fringe ring so no gap shows
      $cx=$bx-$pad; $cy=$by-$pad; $cw=$bw+2*$pad; $ch=$bh+2*$pad
      $ratio=[math]::Max($cw/$shot.Width,$ch/$shot.Height)   # cover (padded)
      $dw=[int]($shot.Width*$ratio); $dh=[int]($shot.Height*$ratio)
      $dx=$cx+[int](($cw-$dw)/2); $dy=$cy+[int](($ch-$dh)/2)
      $g.SetClip((New-Object Drawing.Rectangle($cx,$cy,$cw,$ch)))
      $g.DrawImage($shot,$dx,$dy,$dw,$dh)
      $g.ResetClip()
    }
    $g.DrawImage($baseFrame,0,0,$W,$H)
    Draw-Header $g $f.cap $f.sub $by
    $deviceBottom=$by+$bh
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
    $deviceBottom=$fbTop+$fbH
  }

  Draw-Disclaimer $g $f.disc $deviceBottom
  if($shot){ $shot.Dispose() }
  $bmp.Save((Join-Path $OutputDir $f.file),[Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Write-Host ("Wrote {0}" -f $f.file)
}
if($baseFrame){$baseFrame.Dispose()}
Write-Host "Done -> $OutputDir"
