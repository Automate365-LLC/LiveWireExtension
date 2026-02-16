class TagTaxonomy:
    
    OBJECTION_TYPES = {
        "price": "objection_price",
        "timing": "objection_timing",
        "features": "objection_features",
        "competitor": "objection_competitor",
        "authority": "objection_authority",
        "trust": "objection_trust"
    }
    
    QUALIFICATION = {
        "hot": "qualified_hot",
        "warm": "qualified_warm",
        "cold": "qualified_cold",
        "unqualified": "unqualified"
    }
    
    NEXT_STEPS = {
        "demo": "next_step_demo",
        "proposal": "next_step_proposal",
        "follow_up": "next_step_follow_up",
        "contract": "next_step_contract",
        "closed_won": "next_step_closed_won",
        "closed_lost": "next_step_closed_lost"
    }
    
    COMPETITORS = {
        "salesforce": "competitor_salesforce",
        "hubspot": "competitor_hubspot",
        "pipedrive": "competitor_pipedrive",
        "zoho": "competitor_zoho",
        "dynamics": "competitor_dynamics"
    }
    
    PAIN_POINTS = {
        "manual": "pain_manual_data_entry",
        "lost_deals": "pain_lost_deals",
        "no_insights": "pain_no_insights",
        "slow": "pain_slow_response"
    }
    
    @classmethod
    def normalize_tag(cls, raw_tag: str) -> str:
        raw_lower = raw_tag.lower().strip()
        
        for keyword, tag_id in cls.OBJECTION_TYPES.items():
            if keyword in raw_lower:
                return tag_id
        
        if any(word in raw_lower for word in ["hot", "very interested", "ready"]):
            return cls.QUALIFICATION["hot"]
        elif any(word in raw_lower for word in ["interested", "considering", "evaluating"]):
            return cls.QUALIFICATION["warm"]
        elif any(word in raw_lower for word in ["not sure", "maybe", "thinking"]):
            return cls.QUALIFICATION["cold"]
        
        for keyword, tag_id in cls.COMPETITORS.items():
            if keyword in raw_lower:
                return tag_id
        
        for keyword, tag_id in cls.NEXT_STEPS.items():
            if keyword in raw_lower:
                return tag_id
        
        for keyword, tag_id in cls.PAIN_POINTS.items():
            if keyword in raw_lower:
                return tag_id
        
        return f"other_{raw_lower.replace(' ', '_')[:20]}"
    
    @classmethod
    def normalize_tags(cls, raw_tags: list) -> list:
        return [cls.normalize_tag(tag) for tag in raw_tags]


class NoteFormatter:
    
    @staticmethod
    def format_professional_note(summary: str, objections: list, next_steps: list, 
                                  commitment: str = None) -> str:
        sections = []
        
        sections.append("SUMMARY")
        sections.append(summary.strip())
        sections.append("")
        
        if objections:
            sections.append("OBJECTIONS HANDLED")
            for obj in objections:
                sections.append(f"• {obj}")
            sections.append("")
        
        if next_steps:
            sections.append("NEXT STEPS")
            for step in next_steps:
                sections.append(f"• {step}")
            sections.append("")
        
        if commitment:
            sections.append("COMMITMENT")
            sections.append(commitment)
        
        return "\n".join(sections)


class TaskFormatter:
    
    @staticmethod
    def ensure_atomic_tasks(tasks: list, min_tasks: int = 2, max_tasks: int = 7) -> list:
        cleaned = []
        
        for task in tasks:
            task = task.strip()
            
            if len(task) < 5:
                continue
            
            if not any(char.isupper() or char.isdigit() for char in task):
                task = task.capitalize()
            
            if not task.endswith(('.', '?', '!')):
                task += ""
            
            if TaskFormatter._is_vague(task):
                task = TaskFormatter._make_specific(task)
            
            cleaned.append(task)
        
        if len(cleaned) < min_tasks:
            cleaned.append("Schedule follow-up call to discuss next steps")
        
        return cleaned[:max_tasks]
    
    @staticmethod
    def _is_vague(task: str) -> bool:
        vague_words = ["follow up", "check in", "touch base", "send stuff", "call", "email"]
        task_lower = task.lower()
        return any(vague in task_lower for vague in vague_words) and len(task) < 30
    
    @staticmethod
    def _make_specific(task: str) -> str:
        task_lower = task.lower()
        
        if "follow up" in task_lower:
            return "Follow up on proposal discussion - call next Monday at 10am"
        elif "send" in task_lower:
            return "Send requested materials and pricing information by end of week"
        elif "call" in task_lower or "email" in task_lower:
            return "Contact customer to discuss next steps and timeline"
        
        return task
