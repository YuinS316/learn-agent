import learn_agent.utils.safe_path as _sp


def run_glob(pattern: str) -> str:
    import glob as _g
    try:
        results = []
        for match in _g.glob(pattern, root_dir=_sp.WORKDIR):
            if (_sp.WORKDIR / match).resolve().is_relative_to(_sp.WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as e:
        return f"Error: {e}"