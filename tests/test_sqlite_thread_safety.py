import concurrent.futures
import unittest

from olympus.db.sqlite_dev_repository import SQLiteDevRepository


class TestSQLiteThreadSafety(unittest.TestCase):
    def test_repository_created_in_main_thread_can_serve_worker_thread(self):
        repo = SQLiteDevRepository(":memory:")
        self.addCleanup(repo.close)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            metrics = pool.submit(repo.resumo_metricas).result(timeout=3)

        self.assertEqual(metrics["total_execucoes"], 0)
        self.assertEqual(metrics["total_decisoes"], 0)


if __name__ == "__main__":
    unittest.main()
