# Prepara o Z-Image Turbo para rodar na GPU desta maquina.
#
# Cria um ambiente Python proprio em %USERPROFILE%\.studio-ai\zimage, fora do repositorio,
# para que os ~5 GB de PyTorch com CUDA nao entrem no Git nem no build do Docker. Depois
# baixa a versao do modelo quantizada em 4 bits (~6,8 GB, cache da Hugging Face), que cabe
# numa placa de 8 GB com descarregamento para a CPU.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup_zimage.ps1
#
# Para ligar o servidor depois:
#   & "$env:USERPROFILE\.studio-ai\zimage\Scripts\python.exe" scripts\zimage_server.py

$ErrorActionPreference = 'Stop'
$ambiente = Join-Path $env:USERPROFILE '.studio-ai\zimage'
$python = Join-Path $ambiente 'Scripts\python.exe'
$modelo = if ($env:ZIMAGE_MODEL) { $env:ZIMAGE_MODEL } else { 'unsloth/Z-Image-Turbo-unsloth-bnb-4bit' }

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    throw 'nvidia-smi nao encontrado: e preciso uma placa NVIDIA com driver instalado.'
}

if (-not (Test-Path $python)) {
    Write-Host "Criando ambiente em $ambiente"
    New-Item -ItemType Directory -Force (Split-Path $ambiente) | Out-Null
    py -3.12 -m venv $ambiente
}

& $python -m pip install --upgrade pip
& $python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
& $python -m pip install diffusers transformers accelerate bitsandbytes safetensors pillow

Write-Host "Baixando $modelo (so na primeira vez)"
& $python -c "from huggingface_hub import snapshot_download; snapshot_download('$modelo')"

& $python -c @'
import torch
from diffusers import ZImagePipeline
print('GPU:', torch.cuda.get_device_name(0), '| CUDA ok:', torch.cuda.is_available())
'@

Write-Host ''
Write-Host 'Pronto. Ligue o servidor com:'
Write-Host "  & `"$python`" scripts\zimage_server.py"
