import sys
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.cli_pipeline_service import BatchCliOptions, load_queries_from_inputs, run_batch_cli
import youtube_batch


class CliPipelineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path("D:/YTBDLP/build/test_cli_pipeline_service") / uuid.uuid4().hex
        self.download_dir = self.workdir / "downloads"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._cleanup_workdir)

    def _cleanup_workdir(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)

    def test_load_queries_prefers_inline_inputs(self) -> None:
        query_file = self.workdir / "queries.txt"
        query_file.write_text("file-query\n", encoding="utf-8")

        queries = load_queries_from_inputs(query_file, ["alpha\nbeta", "#ignored\n gamma "])

        self.assertEqual(queries, ["alpha", "beta", "gamma"])

    @patch("app.core.cli_pipeline_service.export_outputs")
    @patch("app.core.cli_pipeline_service.filter_candidates")
    @patch("app.core.cli_pipeline_service.fetch_detail_metadata")
    @patch("app.core.cli_pipeline_service.dedupe_by_video_id")
    @patch("app.core.cli_pipeline_service.search_candidates")
    @patch("app.core.cli_pipeline_service.yt_dlp_base")
    @patch("app.core.cli_pipeline_service.ensure_binary")
    def test_run_batch_cli_search_pipeline_uses_shared_services(
        self,
        ensure_binary_mock,
        yt_dlp_base_mock,
        search_candidates_mock,
        dedupe_mock,
        fetch_detail_metadata_mock,
        filter_candidates_mock,
        export_outputs_mock,
    ) -> None:
        all_jsonl = self.workdir / "03_scored_candidates.jsonl"
        selected_csv = self.workdir / "04_selected_for_review.csv"
        selected_urls = self.workdir / "05_selected_urls.txt"
        all_csv = self.workdir / "04_all_scored.csv"
        yt_dlp_base_mock.return_value = ["yt-dlp"]
        search_candidates_mock.return_value = [{"video_id": "raw-1"}]
        dedupe_mock.return_value = [{"video_id": "deduped-1"}]
        fetch_detail_metadata_mock.return_value = [{"video_id": "detail-1"}]
        filter_candidates_mock.return_value = [{"video_id": "detail-1", "selected": True}]
        export_outputs_mock.return_value = (all_jsonl, selected_csv, selected_urls, all_csv)
        lines: list[str] = []

        result = run_batch_cli(
            BatchCliOptions(
                binary="yt-dlp-custom",
                query_text=("alpha",),
                workdir=self.workdir,
                download_dir=self.download_dir,
                topic_phrase="demo topic",
            ),
            emit=lines.append,
        )

        ensure_binary_mock.assert_called_once_with("yt-dlp-custom")
        yt_dlp_base_mock.assert_called_once()
        search_candidates_mock.assert_called_once()
        dedupe_mock.assert_called_once()
        fetch_detail_metadata_mock.assert_called_once()
        filter_candidates_mock.assert_called_once()
        export_outputs_mock.assert_called_once()
        self.assertEqual(result.mode, "search_pipeline")
        self.assertEqual(result.query_count, 1)
        self.assertEqual(result.selected_count, 1)
        self.assertFalse(result.download_requested)
        self.assertTrue(any("[1/4]" in line for line in lines))
        self.assertTrue(any("[4/4]" in line for line in lines))

    @patch("app.core.cli_pipeline_service.load_url_title_map_from_csv")
    @patch("app.core.cli_pipeline_service.load_urls_file")
    @patch("app.core.cli_pipeline_service.download_selected")
    @patch("app.core.cli_pipeline_service.yt_dlp_base")
    @patch("app.core.cli_pipeline_service.ensure_binary")
    def test_run_batch_cli_download_only_path_reuses_download_service(
        self,
        ensure_binary_mock,
        yt_dlp_base_mock,
        download_selected_mock,
        load_urls_file_mock,
        load_url_title_map_mock,
    ) -> None:
        urls_file = self.workdir / "urls.txt"
        urls_file.write_text("https://www.youtube.com/watch?v=vid-a\n", encoding="utf-8")
        yt_dlp_base_mock.return_value = ["yt-dlp"]
        load_urls_file_mock.return_value = ["https://www.youtube.com/watch?v=vid-a"]
        load_url_title_map_mock.return_value = {"https://www.youtube.com/watch?v=vid-a": "Video A"}
        lines: list[str] = []

        result = run_batch_cli(
            BatchCliOptions(
                workdir=self.workdir,
                download_dir=self.download_dir,
                download_from_urls_file=urls_file,
                clean_video=True,
            ),
            emit=lines.append,
        )

        ensure_binary_mock.assert_called_once()
        yt_dlp_base_mock.assert_called_once()
        download_selected_mock.assert_called_once()
        call = download_selected_mock.call_args.kwargs
        self.assertEqual(call["download_dir"], self.download_dir)
        self.assertEqual(call["archive_file"], self.workdir / "download_archive.txt")
        self.assertEqual(call["sponsorblock_remove"], "sponsor,selfpromo,intro,outro,interaction")
        self.assertEqual(result.mode, "download_only")
        self.assertTrue(result.download_requested)
        self.assertTrue(any("[下载模式]" in line for line in lines))

    def test_youtube_batch_parse_args_keeps_cli_surface(self) -> None:
        args = youtube_batch.parse_args(["--query-text", "alpha", "--download", "--download-dir", str(self.download_dir)])

        self.assertEqual(args.query_text, ["alpha"])
        self.assertTrue(args.download)
        self.assertEqual(args.download_dir, self.download_dir)

    def test_youtube_batch_main_delegates_to_cli_pipeline_service(self) -> None:
        with patch("youtube_batch.run_batch_cli") as run_batch_cli_mock:
            exit_code = youtube_batch.main(["--query-text", "alpha"])

        self.assertEqual(exit_code, 0)
        run_batch_cli_mock.assert_called_once()
        passed_options = run_batch_cli_mock.call_args.args[0]
        self.assertEqual(passed_options.query_text, ("alpha",))


if __name__ == "__main__":
    unittest.main()
