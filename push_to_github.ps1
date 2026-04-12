# GitHub 배포 스크립트 (학생 배포용)
# 실행 전: GitHub에서 'ai-video-generator' 저장소를 먼저 생성하세요
# https://github.com/new

$GITHUB_USER = "aiautou"   # GitHub 사용자명 (필요시 수정)
$REPO_NAME   = "ai-video-generator"
$REPO_URL    = "https://github.com/$GITHUB_USER/$REPO_NAME.git"
$DIR         = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $DIR

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GitHub Push (Student Distribution)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 기존 git repo가 있으면 히스토리 초기화 (민감 정보 제거)
if (Test-Path ".git") {
    Write-Host "Removing old git history (security: .env was committed)..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".git"
}

# 새 git 초기화
git init
git checkout -b main

# GitHub remote 설정
git remote add origin $REPO_URL

# 파일 추가 (.env는 .gitignore로 자동 제외)
git add -A
git status

Write-Host ""
Write-Host "Files to be committed (verify .env is NOT listed above):" -ForegroundColor Yellow
Write-Host ""

git commit -m "Initial release: AI video automation pipeline"

Write-Host ""
Write-Host "Pushing to GitHub..." -ForegroundColor Green
Write-Host "(Username: $GITHUB_USER / Password: GitHub Personal Access Token)" -ForegroundColor Gray
Write-Host "Token 발급: https://github.com/settings/tokens → Generate new token (classic) → repo 권한" -ForegroundColor Gray
Write-Host ""
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  배포 완료!" -ForegroundColor Green
    Write-Host "  학생 공유 링크:" -ForegroundColor White
    Write-Host "  https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Push 실패. GitHub 토큰 또는 저장소 URL을 확인하세요." -ForegroundColor Red
}

pause
