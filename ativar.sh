#!/bin/sh
# Copia agentes e comandos para a pasta oculta .claude (rode sempre que algo em agentes/ ou comandos/ mudar)
cd "$(dirname "$0")"
mkdir -p .claude/agents .claude/commands
cp agentes/*.md .claude/agents/
cp comandos/*.md .claude/commands/
echo "Ativado: $(ls agentes | wc -l | tr -d ' ') agentes, $(ls comandos | wc -l | tr -d ' ') comandos"

# Patch: permite "grade" por trecho no edl.json (necessário para misturar tomadas giradas, recortadas e B-roll)
R=.claude/skills/video-use-vivavoz-edits/helpers/render.py
if [ -f "$R" ] && ! grep -q "PATCH-VIVAVOZ grade por trecho" "$R"; then
  python3 - "$R" <<'PY'
import sys;p=sys.argv[1];s=open(p).read()
old="            seg_filter = resolved\n"
new="            seg_filter = resolve_grade_filter(r[\"grade\"]) if r.get(\"grade\") else resolved  # PATCH-VIVAVOZ grade por trecho\n"
assert old in s, "trecho não encontrado; avise o Claude"
open(p,"w").write(s.replace(old,new,1)); print("Patch aplicado: grade por trecho")
PY
fi
