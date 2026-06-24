from unittest.mock import patch, MagicMock

# Celery task definitions
from app.worker import run_analysis_task, run_sector_analysis_task

def test_celery_analysis_task_retry():
    with patch("main.get_analysis_job_service") as mock_get_service, \
         patch("app.db.repositories.job_repo.JobRepository.update_status") as mock_update, \
         patch("app.worker.asyncio.run") as mock_run_job:
    
        mock_run_job.side_effect = Exception("429 Too Many Requests")
    
        from celery.exceptions import Retry
        import pytest
        
        with pytest.raises(Retry):
            # Celery will inject self automatically if called as __call__ or via apply
            # Since we call .run(), we can pass a dummy, but celery's retry still raises Retry
            # So we just verify that Retry is raised!
            mock_self = MagicMock()
            mock_self.request.retries = 1
            run_analysis_task.run(mock_self, "job_123", "AAPL", "US")

def test_celery_sector_analysis_task_dispatch():
    with patch("app.services.sector_analysis_service.SectorAnalysisService._run_sector_job") as mock_run_job, \
         patch("app.db.repositories.job_repo.JobRepository.update_status") as mock_update:
         
        # Test normal sector execution without error
        run_sector_analysis_task("job_456", "AI")
        
        assert mock_run_job.called
        args, kwargs = mock_run_job.call_args
        assert args[0] == "job_456"
        assert args[1] == "AI"
