# 가짜 마이크로 넣을 답변 음성(answer.wav)을 Windows 한국어 음성(Microsoft Heami)으로 만든다. 한 번만 실행하면 된다.
# 사용: powershell -ExecutionPolicy Bypass -File make_answer_wav.ps1
# 답변 글은 answer.txt(UTF-8)에 있다. Windows PowerShell 5.1은 BOM 없는 스크립트를 CP949로 읽어 한글을 여기 직접 쓰면 깨진다
Add-Type -AssemblyName System.Speech
$text = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "answer.txt")
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Heami Desktop")
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile((Join-Path $PSScriptRoot "answer.wav"), $fmt)
$s.Speak($text)
$s.Dispose()
