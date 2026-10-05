from typing import Iterable, Tuple
from olympus.skills.registry import SkillRegistry
from olympus.skills.models import SkillSpec


class SkillResolver:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def resolve(
        self,
        task: str,
        explicit: Iterable[str] = (),
        *,
        required: Iterable[str] = (),
        supporting: Iterable[str] = (),
        excluded: Iterable[str] = (),
        max_inferred: int = 6,
    ) -> Tuple[SkillSpec, ...]:
        """Resolve a bounded skill graph.

        Required/explicit skills are authoritative inputs from the deterministic
        mission compiler. Supporting skills are added next. Trigger inference is
        only a fallback and never overrides exclusions. Dependencies remain
        transitive, but an excluded optional skill is not resurrected by matching
        prose. A dependency of a required skill is still honored.
        """
        out = []
        seen = set()
        excluded_ids = set(excluded or ())
        required_ids = tuple(dict.fromkeys(tuple(explicit or ()) + tuple(required or ())))

        def add(skill_id: str, *, force: bool = False):
            if not force and skill_id in excluded_ids:
                return
            try:
                skill = self.registry.get(skill_id)
            except Exception:
                return
            if skill.status != "active" or skill.id in seen:
                return
            out.append(skill)
            seen.add(skill.id)

        for sid in required_ids:
            add(sid, force=True)
        for sid in supporting or ():
            add(sid)

        inferred = 0
        scored = sorted(
            ((s.matches(task), s.id, s) for s in self.registry.active() if s.matches(task)),
            key=lambda x: (-x[0], x[1]),
        )
        for _, _, skill in scored:
            if inferred >= max_inferred:
                break
            if skill.id in seen or skill.id in excluded_ids:
                continue
            out.append(skill)
            seen.add(skill.id)
            inferred += 1

        i = 0
        while i < len(out):
            parent = out[i]
            parent_required = parent.id in required_ids
            for dep in parent.depends_on:
                # A required skill may force a dependency. Otherwise exclusions
                # prevent accidental product/web skill explosions.
                add(dep, force=parent_required)
            i += 1
        return tuple(out)
