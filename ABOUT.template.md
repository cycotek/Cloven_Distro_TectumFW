### ✅ `ABOUT.template.md`


```markdown
# 🧠 Cloven_Tectum Framework


> *“The tectum in the human brain orients the body and eyes toward relevant stimuli.
This framework applies the same principle: orient AI systems toward **meaningful signal**, shielding them from distortion and noise.”*


---


## ⚙️ Build Info
- Version: {{VERSION}}
- Commit: {{GIT_HASH}}
- Date: {{DATE}}


---


## 📌 Purpose


This project represents the vision of a fault-tolerant, DevOps-first AI operating environment. ABOUT.md is not just metadata — it's a statement of intent and design philosophy.


> _"No gods, no devils, only uptime."_


Key principles:
- Clarity in chaos
- Stability in distortion
- Resilience against systemic noise


---


## 🔍 Contents
- Versioning metadata
- Stack overview and mission
- Links to core stack entrypoints


---


## 🌐 Access Points
- **API Docs** → [http://localhost:8000/docs](http://localhost:8000/docs)
- **WebUI (OpenWebUI)** → [http://localhost:8080](http://localhost:8080)


---


> _“One is glad to be of service.”_
> — Tectum Node 0x01
```


---


### ✅ Final Touch: Add into `serversetup.sh`


At the **end** of the file:


```bash
# ---- Update metadata ----
echo "📦 Generating README and ABOUT files..."
chmod +x ./update_readme.sh
./update_readme.sh
```


This ensures README.md and ABOUT.md are:
- Versioned
- Git-synced
- Rewritten every time a new build occurs
