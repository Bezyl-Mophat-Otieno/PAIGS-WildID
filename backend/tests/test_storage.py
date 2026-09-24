"""app.storage -- focused on copy_run_files, the piece POST /runs/{id}/rerun
needs to reuse a prior run's already-stored file(s) under a brand-new run
id (app.orchestration.rerun.create_rerun). save_uploaded_files/run_dir are
already exercised indirectly through every Stage 0 API test; this file is
just for the one function that's new.
"""
from app import storage


class TestCopyRunFiles:
    def test_copies_bytes_into_the_destination_runs_own_directory(self, temp_storage_root):
        source_dir = storage.run_dir("source-run")
        source_dir.mkdir(parents=True)
        (source_dir / "forward.ab1").write_bytes(b"raw-ab1-bytes")

        copied = storage.copy_run_files("source-run", "dest-run", ["forward.ab1"])

        assert copied == ["forward.ab1"]
        dest_path = storage.run_dir("dest-run") / "forward.ab1"
        assert dest_path.is_file()
        assert dest_path.read_bytes() == b"raw-ab1-bytes"

    def test_copies_multiple_files_preserving_order(self, temp_storage_root):
        source_dir = storage.run_dir("source-run-2")
        source_dir.mkdir(parents=True)
        (source_dir / "forward.ab1").write_bytes(b"fwd")
        (source_dir / "reverse.ab1").write_bytes(b"rev")

        copied = storage.copy_run_files("source-run-2", "dest-run-2", ["forward.ab1", "reverse.ab1"])

        assert copied == ["forward.ab1", "reverse.ab1"]
        dest_dir = storage.run_dir("dest-run-2")
        assert (dest_dir / "forward.ab1").read_bytes() == b"fwd"
        assert (dest_dir / "reverse.ab1").read_bytes() == b"rev"

    def test_leaves_the_source_files_untouched(self, temp_storage_root):
        source_dir = storage.run_dir("source-run-3")
        source_dir.mkdir(parents=True)
        source_file = source_dir / "forward.ab1"
        source_file.write_bytes(b"original")

        storage.copy_run_files("source-run-3", "dest-run-3", ["forward.ab1"])

        assert source_file.read_bytes() == b"original"

    def test_does_not_collide_with_an_existing_file_of_the_same_name_in_the_destination(
        self, temp_storage_root
    ):
        source_dir = storage.run_dir("source-run-4")
        source_dir.mkdir(parents=True)
        (source_dir / "forward.ab1").write_bytes(b"new-content")

        dest_dir = storage.run_dir("dest-run-4")
        dest_dir.mkdir(parents=True)
        (dest_dir / "forward.ab1").write_bytes(b"already-there")

        copied = storage.copy_run_files("source-run-4", "dest-run-4", ["forward.ab1"])

        assert copied == ["forward__1.ab1"]
        assert (dest_dir / "forward.ab1").read_bytes() == b"already-there"
        assert (dest_dir / "forward__1.ab1").read_bytes() == b"new-content"
