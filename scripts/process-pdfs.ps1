param(
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ContentRoot = Join-Path $Root "content\jiangsu"
$SourcesRoot = Join-Path $Root "sources\jiangsu"
$PublicOfficialDir = Join-Path $SourcesRoot "public-official"
$MajorPdfDir = Join-Path $PublicOfficialDir "major-plans"
$ProcessedDir = Join-Path $SourcesRoot "processed"
$PolicyPdfDir = Join-Path $PublicOfficialDir "policies"
$TextbookPdfDir = Join-Path $PublicOfficialDir "textbooks"
$SyllabusPdfDir = Join-Path $PublicOfficialDir "syllabi"
$PastPaperPdfDir = Join-Path $PublicOfficialDir "past-papers"

# Single source of truth: ops/jiangsu/major-slugs.json (P2)
$MajorSlugsPath = Join-Path $Root "ops\jiangsu\major-slugs.json"
$NameSlugMap = @{}
if (Test-Path -LiteralPath $MajorSlugsPath) {
  $slugJson = Get-Content -LiteralPath $MajorSlugsPath -Raw -Encoding UTF8 | ConvertFrom-Json
  foreach ($prop in $slugJson.slugs.PSObject.Properties) {
    $NameSlugMap[$prop.Name] = [string]$prop.Value
  }
} else {
  Write-Warning "major-slugs.json missing; NameSlugMap empty"
}

function Resolve-Tool {
  param([string]$Name)

  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  $candidateRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
  if (Test-Path -LiteralPath $candidateRoot) {
    $candidate = Get-ChildItem -LiteralPath $candidateRoot -Recurse -Filter "$Name.exe" -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if ($candidate) {
      return $candidate.FullName
    }
  }

  throw "Cannot find $Name. Install Poppler first."
}

function Write-Utf8File {
  param(
    [string]$Path,
    [string]$Content
  )

  $dir = Split-Path -Parent $Path
  if ($dir) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Get-RelativePath {
  param([string]$Path)
  return $Path.Replace($Root + "\", "")
}

function Escape-Html {
  param([string]$Value)
  return [System.Net.WebUtility]::HtmlEncode($Value)
}


function Get-Sha256 {
  param([string]$Path)
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-NonEmptyFile {
  param(
    [string]$Path,
    [string]$Label
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "$Label missing: $Path"
  }
  if ((Get-Item -LiteralPath $Path).Length -le 0) {
    throw "$Label empty: $Path"
  }
}

function Test-IsUnderDirectory {
  param(
    [string]$Path,
    [string]$Directory
  )

  if (-not (Test-Path -LiteralPath $Directory)) { return $false }
  $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
  $fullDir = [System.IO.Path]::GetFullPath($Directory).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
  return $fullPath.Equals($fullDir, [System.StringComparison]::OrdinalIgnoreCase) -or `
    $fullPath.StartsWith($fullDir + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or `
    $fullPath.StartsWith($fullDir + [System.IO.Path]::AltDirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-DocumentPolicy {
  param([string]$Type)

  if ($Type -in @("textbooks", "past-papers")) {
    return @{ EmitFullText = $false; Policy = "metadata-only" }
  }
  return @{ EmitFullText = $true; Policy = "full-text-draft" }
}

function Get-SafeSlug {
  param([string]$Value)

  $slug = $Value.ToLowerInvariant()
  $slug = $slug -replace "[^a-z0-9]+", "-"
  $slug = $slug.Trim("-")
  if ([string]::IsNullOrWhiteSpace($slug)) {
    return "document"
  }
  return $slug
}


function Get-UniqueSlug {
  param(
    [string]$Stem,
    [string]$SourcePath
  )

  $slug = Get-SafeSlug $Stem
  if ($slug -eq "document") {
    $hash = (Get-Sha256 $SourcePath).Substring(0, 12)
    return "document-$hash"
  }
  return $slug
}

function Invoke-PdfRawConversion {
  param(
    [System.IO.FileInfo]$Pdf,
    [string]$OutputPrefix,
    [string]$TextOutput,
    [string]$PdfToHtml,
    [string]$PdfToText
  )

  $xmlOutput = "$OutputPrefix.xml"
  if ($Force) {
    foreach ($path in @($xmlOutput, $TextOutput)) {
      if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
      }
    }
  }

  if (-not (Test-Path -LiteralPath $xmlOutput)) {
    & $PdfToHtml -xml -i -noframes $Pdf.FullName $OutputPrefix | Out-Null
  }

  if (-not (Test-Path -LiteralPath $TextOutput)) {
    & $PdfToText -layout $Pdf.FullName $TextOutput
  }

  return @{
    RawXml = $xmlOutput
    RawTxt = $TextOutput
  }
}

function New-RawViewHtml {
  param(
    [hashtable]$Meta,
    [string]$RawText
  )

  $title = Escape-Html $Meta.Title
  $sourcePdf = Escape-Html $Meta.SourcePdf
  $docType = Escape-Html $Meta.Type
  $code = Escape-Html $Meta.Code
  $name = Escape-Html $Meta.Name
  $level = Escape-Html $Meta.Level
  $generatedAt = Escape-Html $Meta.GeneratedAt
  $pages = $RawText -split "`f"
  $sections = New-Object System.Text.StringBuilder
  $pageNumber = 1

  foreach ($page in $pages) {
    $body = ($page -replace "`r", "").Trim()
    if ([string]::IsNullOrWhiteSpace($body)) {
      $pageNumber += 1
      continue
    }

    $escapedBody = Escape-Html $body
    [void]$sections.AppendLine("    <section data-section=""raw-text-page"" data-source-page=""$pageNumber"">")
    [void]$sections.AppendLine("      <h2>第 $pageNumber 页</h2>")
    [void]$sections.AppendLine("      <pre>$escapedBody</pre>")
    [void]$sections.AppendLine("    </section>")
    $pageNumber += 1
  }

  return @"
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>$title</title>
</head>
<body>
  <article data-document-type="$docType" data-source-pdf="$sourcePdf" data-generated-at="$generatedAt">
    <header>
      <h1>$title</h1>
      <dl>
        <dt>文档类型</dt>
        <dd>$docType</dd>
        <dt>专业代码</dt>
        <dd>$code</dd>
        <dt>专业名称</dt>
        <dd>$name</dd>
        <dt>层次</dt>
        <dd>$level</dd>
      </dl>
    </header>
$sections
  </article>
</body>
</html>
"@
}

function New-ExtractedMarkdown {
  param(
    [hashtable]$Meta,
    [string]$RawText,
    [string]$RawXmlRel,
    [string]$RawTxtRel,
    [string]$RawViewHtmlRel
  )

  $text = (($RawText -replace "`r", "").Trim() -split "`n" | ForEach-Object { "    $_" }) -join "`n"
  $body = if ($Meta.EmitFullText) {
    "## 机器抽取文本`n`n$text"
  } else {
    "## 机器抽取文本`n`n本资料类型按版权策略不写入全文；请查看 Raw TXT/Raw XML 做内部校对。"
  }

  return @"
# $($Meta.Title)

| 字段 | 内容 |
| --- | --- |
| 文档类型 | $($Meta.Type) |
| 源 PDF | $($Meta.SourcePdf) |
| 源 PDF SHA256 | $($Meta.SourceSha256) |
| 专业代码 | $($Meta.Code) |
| 专业名称 | $($Meta.Name) |
| 层次 | $($Meta.Level) |
| 抽取策略 | $($Meta.ExtractionPolicy) |
| 数据状态 | 机器抽取草稿，待人工校对 |

## 转换产物

- Raw XML：$RawXmlRel
- Raw TXT：$RawTxtRel
- Raw View HTML：$RawViewHtmlRel

$body
"@
}

function New-PipelineNotes {
  param(
    [hashtable]$Meta,
    [string]$RawXmlRel,
    [string]$RawTxtRel,
    [string]$RawViewHtmlRel,
    [string]$ExtractedMarkdownRel
  )

  return @"
# PDF 转换记录

| 字段 | 内容 |
| --- | --- |
| 源 PDF | $($Meta.SourcePdf) |
| 源 PDF SHA256 | $($Meta.SourceSha256) |
| 转换日期 | $($Meta.GeneratedAt) |
| 转换工具 | Poppler pdftohtml -xml -i -noframes；pdftotext -layout |
| 抽取策略 | $($Meta.ExtractionPolicy) |
| 原始 XML | $RawXmlRel |
| 原始 TXT | $RawTxtRel |
| Raw View HTML | $RawViewHtmlRel |
| Markdown 草稿 | $ExtractedMarkdownRel |
| 数据状态 | 机器初稿，待人工校对 |

## 自动抽取问题

- [ ] 表格列是否错位：
- [ ] 页眉页脚是否混入正文：
- [ ] 课程代码是否缺失：
- [ ] 专业代码、专业名称、层次是否与官方 PDF 一致：

## 人工修正记录

| 位置 | 修改 | 原因 | 校对人/日期 |
| --- | --- | --- | --- |
"@
}

function Write-MajorStub {
  param(
    [hashtable]$Meta,
    [string]$MajorDir,
    [string]$RawXmlRel,
    [string]$RawTxtRel,
    [string]$RawViewHtmlRel,
    [string]$ExtractedMarkdownRel
  )

  $indexPath = Join-Path $MajorDir "index.md"
  if (-not (Test-Path -LiteralPath $indexPath)) {
    $content = @"
# $($Meta.Name)（$($Meta.Level)）

| 字段 | 内容 |
| --- | --- |
| 省份 | 江苏 |
| 专业代码 | $($Meta.Code) |
| 专业名称 | $($Meta.Name) |
| 层次 | $($Meta.Level) |
| 数据状态 | PDF 已完成机器抽取，待人工校对 |

## 处理产物

- Raw XML：$RawXmlRel
- Raw TXT：$RawTxtRel
- Raw View HTML：$RawViewHtmlRel
- Markdown 草稿：$ExtractedMarkdownRel

## 待校对

- 专业基本信息。
- 课程清单与学分。
- 实践与毕业环节。
- 主考学校与教材来源。
"@
    Write-Utf8File $indexPath $content
  }

  $sourcesPath = Join-Path $MajorDir "sources.md"
  if (-not (Test-Path -LiteralPath $sourcesPath)) {
    $content = @"
# $($Meta.Name)（$($Meta.Level)）资料源清单

> 适用页面：[ $($Meta.Name)（$($Meta.Level)）](./index.md)

## 官方来源

| 来源 | 本地文件 |
| --- | --- |
| 专业考试计划 PDF | $($Meta.SourcePdf) |
| Raw XML | $RawXmlRel |
| Raw TXT | $RawTxtRel |
| Raw View HTML | $RawViewHtmlRel |
| Markdown 草稿 | $ExtractedMarkdownRel |

## 待补全

- 主考学校来源。
- 教材与考试大纲来源。
- 真题线索和版权审核。
"@
    Write-Utf8File $sourcesPath $content
  }
}

function Process-Document {
  param(
    [System.IO.FileInfo]$Pdf,
    [string]$OutDir,
    [string]$PrefixName,
    [hashtable]$Meta,
    [string]$PdfToHtml,
    [string]$PdfToText
  )

  New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
  $prefix = Join-Path $OutDir $PrefixName
  $textOutput = "$prefix.txt"
  $Meta.SourceSha256 = Get-Sha256 $Pdf.FullName
  $policy = Get-DocumentPolicy $Meta.Type
  $Meta.EmitFullText = $policy.EmitFullText
  $Meta.ExtractionPolicy = $policy.Policy

  $raw = Invoke-PdfRawConversion -Pdf $Pdf -OutputPrefix $prefix -TextOutput $textOutput -PdfToHtml $PdfToHtml -PdfToText $PdfToText
  Assert-NonEmptyFile $raw.RawXml "Raw XML"
  Assert-NonEmptyFile $raw.RawTxt "Raw TXT"
  $rawText = Get-Content -Raw -LiteralPath $raw.RawTxt
  if ([string]::IsNullOrWhiteSpace($rawText)) { throw "Raw TXT has no extractable text: $($Pdf.FullName)" }

  $rawViewPath = Join-Path $OutDir ($PrefixName -replace "\.raw$", ".raw-view.html")
  $extractedPath = Join-Path $OutDir ($PrefixName -replace "\.raw$", ".extracted.md")
  $notesPath = Join-Path $OutDir ($PrefixName -replace "\.raw$", ".pipeline-notes.md")

  Write-Utf8File $rawViewPath (New-RawViewHtml -Meta $Meta -RawText $rawText)

  $rawXmlRel = Get-RelativePath $raw.RawXml
  $rawTxtRel = Get-RelativePath $raw.RawTxt
  $rawViewRel = Get-RelativePath $rawViewPath
  $extractedRel = Get-RelativePath $extractedPath

  Write-Utf8File $extractedPath (New-ExtractedMarkdown -Meta $Meta -RawText $rawText -RawXmlRel $rawXmlRel -RawTxtRel $rawTxtRel -RawViewHtmlRel $rawViewRel)
  Write-Utf8File $notesPath (New-PipelineNotes -Meta $Meta -RawXmlRel $rawXmlRel -RawTxtRel $rawTxtRel -RawViewHtmlRel $rawViewRel -ExtractedMarkdownRel $extractedRel)

  return @{
    RawXml = $raw.RawXml
    RawTxt = $raw.RawTxt
    RawViewHtml = $rawViewPath
    ExtractedMarkdown = $extractedPath
    PipelineNotes = $notesPath
    SourceSha256 = $Meta.SourceSha256
    ExtractionPolicy = $Meta.ExtractionPolicy
  }
}

$PdfToHtml = Resolve-Tool "pdftohtml"
$PdfToText = Resolve-Tool "pdftotext"
$GeneratedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
$Manifest = New-Object System.Collections.Generic.List[object]
$MajorRows = New-Object System.Collections.Generic.List[object]

$majorPdfs = Get-ChildItem -LiteralPath $MajorPdfDir -Filter "*.pdf" -File -Recurse |
  Where-Object { $_.FullName -notmatch "[\\/]source[\\/]" -and $_.BaseName -match "^\d+\." } |
  Sort-Object Name
foreach ($pdf in $majorPdfs) {
  $fileMatch = [regex]::Match($pdf.Name, "^(\d+)\.(.+?)专业（(.+?)）考试计划\.pdf$")
  if (-not $fileMatch.Success) {
    Write-Warning "Cannot parse major PDF filename: $($pdf.Name)"
    continue
  }

  $sequence = $fileMatch.Groups[1].Value
  $majorName = $fileMatch.Groups[2].Value
  $level = $fileMatch.Groups[3].Value
  $probeText = & $PdfToText -layout $pdf.FullName -
  $codeMatch = [regex]::Match(($probeText -join "`n"), "专业代码[：:]\s*([0-9A-Z]+)")
  $code = if ($codeMatch.Success) { $codeMatch.Groups[1].Value } else { throw "Cannot extract major code from $($pdf.Name)" }
  $slug = if ($NameSlugMap.ContainsKey($majorName)) { $NameSlugMap[$majorName] } else { "major-$sequence" }
  $majorDirName = "$code-$slug"
  $majorDir = Join-Path $ContentRoot "majors\$majorDirName"
  $outDir = Join-Path $majorDir "sources"
  $sourcePdfRel = Get-RelativePath $pdf.FullName
  $title = "$majorName（$level）"
  $meta = @{
    Type = "major-plan"
    SourcePdf = $sourcePdfRel
    Code = $code
    Name = $majorName
    Level = $level
    Title = $title
    GeneratedAt = $GeneratedAt
  }

  Write-Host "Processing major $sequence $title -> $majorDirName"
  $outputs = Process-Document -Pdf $pdf -OutDir $outDir -PrefixName "plan.raw" -Meta $meta -PdfToHtml $PdfToHtml -PdfToText $PdfToText

  $rawXmlRel = Get-RelativePath $outputs.RawXml
  $rawTxtRel = Get-RelativePath $outputs.RawTxt
  $rawViewRel = Get-RelativePath $outputs.RawViewHtml
  $extractedRel = Get-RelativePath $outputs.ExtractedMarkdown
  Write-MajorStub -Meta $meta -MajorDir $majorDir -RawXmlRel $rawXmlRel -RawTxtRel $rawTxtRel -RawViewHtmlRel $rawViewRel -ExtractedMarkdownRel $extractedRel

  $Manifest.Add([pscustomobject]@{
    type = "major-plan"
    title = $title
    code = $code
    source_pdf = $sourcePdfRel
    output_dir = Get-RelativePath $outDir
    raw_xml = $rawXmlRel
    raw_txt = $rawTxtRel
    raw_view_html = $rawViewRel
    extracted_md = $extractedRel
    source_sha256 = $outputs.SourceSha256
    extraction_policy = $outputs.ExtractionPolicy
  })
  $MajorRows.Add([pscustomobject]@{
    sequence = $sequence
    code = $code
    name = $majorName
    level = $level
    dir = Get-RelativePath $majorDir
  })
}

$sharedPdfs = @()
if (Test-Path -LiteralPath $PolicyPdfDir) {
  $sharedPdfs += Get-ChildItem -LiteralPath $PolicyPdfDir -Filter "*.pdf" -File -Recurse
}
$majorSourceDir = Join-Path $MajorPdfDir "source"
if (Test-Path -LiteralPath $majorSourceDir) {
  $sharedPdfs += Get-ChildItem -LiteralPath $majorSourceDir -Filter "*.pdf" -File -Recurse
}
$textbookPdfDir = $TextbookPdfDir
if (Test-Path -LiteralPath $textbookPdfDir) {
  $sharedPdfs += Get-ChildItem -LiteralPath $textbookPdfDir -Filter "*.pdf" -File
}
$syllabusPdfDir = $SyllabusPdfDir
if (Test-Path -LiteralPath $syllabusPdfDir) {
  $sharedPdfs += Get-ChildItem -LiteralPath $syllabusPdfDir -Filter "*.pdf" -File
}
$pastPaperPdfDir = $PastPaperPdfDir
if (Test-Path -LiteralPath $pastPaperPdfDir) {
  $sharedPdfs += Get-ChildItem -LiteralPath $pastPaperPdfDir -Filter "*.pdf" -File -Recurse
}

foreach ($pdf in ($sharedPdfs | Sort-Object FullName)) {
  $stemSlug = Get-UniqueSlug -Stem $pdf.BaseName -SourcePath $pdf.FullName
  $category = if (Test-IsUnderDirectory $pdf.FullName $TextbookPdfDir) {
    "textbooks"
  } elseif (Test-IsUnderDirectory $pdf.FullName $SyllabusPdfDir) {
    "syllabi"
  } elseif (Test-IsUnderDirectory $pdf.FullName $PolicyPdfDir) {
    "policies"
  } elseif (Test-IsUnderDirectory $pdf.FullName (Join-Path $MajorPdfDir "source")) {
    "major-source"
  } elseif (Test-IsUnderDirectory $pdf.FullName $PastPaperPdfDir) {
    "past-papers"
  } else {
    "documents"
  }
  $outDir = if ($category -eq "past-papers") {
    $relativePastPaper = [System.IO.Path]::GetRelativePath($PastPaperPdfDir, $pdf.FullName)
    $relativeStem = [System.IO.Path]::Combine(
      (Split-Path -Parent $relativePastPaper),
      [System.IO.Path]::GetFileNameWithoutExtension($relativePastPaper)
    )
    $relativeSlug = (($relativeStem -split "[\\/]" | ForEach-Object { Get-SafeSlug $_ }) -join "\")
    Join-Path $ProcessedDir "$category\$relativeSlug"
  } else {
    Join-Path $ProcessedDir "$category\$stemSlug"
  }
  $sourcePdfRel = Get-RelativePath $pdf.FullName
  $meta = @{
    Type = $category
    SourcePdf = $sourcePdfRel
    Code = ""
    Name = $pdf.BaseName
    Level = ""
    Title = $pdf.BaseName
    GeneratedAt = $GeneratedAt
  }

  Write-Host "Processing shared PDF $($pdf.Name) -> $category/$stemSlug"
  $outputs = Process-Document -Pdf $pdf -OutDir $outDir -PrefixName "document.raw" -Meta $meta -PdfToHtml $PdfToHtml -PdfToText $PdfToText

  $Manifest.Add([pscustomobject]@{
    type = $category
    title = $pdf.BaseName
    code = ""
    source_pdf = $sourcePdfRel
    output_dir = Get-RelativePath $outDir
    raw_xml = Get-RelativePath $outputs.RawXml
    raw_txt = Get-RelativePath $outputs.RawTxt
    raw_view_html = Get-RelativePath $outputs.RawViewHtml
    extracted_md = Get-RelativePath $outputs.ExtractedMarkdown
    source_sha256 = $outputs.SourceSha256
    extraction_policy = $outputs.ExtractionPolicy
  })
}

$manifestCsv = Join-Path $ProcessedDir "source-records\pdf-processing-manifest.csv"
$Manifest | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $manifestCsv

$majorIndex = Join-Path $ContentRoot "majors\index.md"
$majorLines = New-Object System.Text.StringBuilder
[void]$majorLines.AppendLine("# 江苏自考专业索引")
[void]$majorLines.AppendLine("")
[void]$majorLines.AppendLine("| 序号 | 专业代码 | 专业名称 | 层次 | 页面 |")
[void]$majorLines.AppendLine("| ---: | --- | --- | --- | --- |")
foreach ($row in ($MajorRows | Sort-Object sequence)) {
  $dirName = Split-Path -Leaf $row.dir
  [void]$majorLines.AppendLine("| $($row.sequence) | $($row.code) | $($row.name) | $($row.level) | [页面](./$dirName/) |")
}
Write-Utf8File $majorIndex $majorLines.ToString()

$report = Join-Path $ProcessedDir "source-records\pdf-processing-report.md"
$majorCount = ($Manifest | Where-Object { $_.type -eq "major-plan" }).Count
$sharedCount = $Manifest.Count - $majorCount
$reportContent = @"
# PDF 批处理报告

| 字段 | 内容 |
| --- | --- |
| 处理时间 | $GeneratedAt |
| 专业计划 PDF | $majorCount |
| 共享 PDF | $sharedCount |
| Manifest | sources/jiangsu/processed/source-records/pdf-processing-manifest.csv |

## 输出规则

- 专业计划 PDF：content/jiangsu/majors/<major>/sources/
- 共享 PDF：sources/jiangsu/processed/<category>/<document>/

## 数据状态

本次输出为机器初稿，已完成 raw XML/TXT、Raw View HTML、Markdown 草稿和转换记录；manifest 记录 SHA256 与抽取策略。教材/真题默认不写入全文草稿，课程表级语义化抽取仍需后续人工校对或规则增强。
"@
Write-Utf8File $report $reportContent

Write-Host "Processed $($Manifest.Count) PDFs."
Write-Host "Manifest: $(Get-RelativePath $manifestCsv)"
Write-Host "Report: $(Get-RelativePath $report)"
