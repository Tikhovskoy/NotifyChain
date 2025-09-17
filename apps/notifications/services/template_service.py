import logging
import re
from typing import Dict, Any, Optional
from django.template import Template, Context
from django.template.exceptions import TemplateSyntaxError

from ..models import NotificationTemplate

logger = logging.getLogger('notifychain.notifications')


class TemplateService:

    def render_template(
        self,
        template: NotificationTemplate,
        context_data: Dict[str, Any]
    ) -> Dict[str, str]:

        try:
            subject = self._render_string(template.subject, context_data)
            body = self._render_string(template.body, context_data)

            return {
                'subject': subject,
                'body': body
            }

        except Exception as e:
            logger.error(f"Ошибка рендеринга шаблона {template.name}: {str(e)}")
            raise ValueError(f"Ошибка рендеринга шаблона: {str(e)}")

    def render_message(
        self,
        message_template: str,
        context_data: Dict[str, Any]
    ) -> str:

        try:
            return self._render_string(message_template, context_data)
        except Exception as e:
            logger.error(f"Ошибка рендеринга шаблона сообщения: {str(e)}")
            raise ValueError(f"Ошибка рендеринга сообщения: {str(e)}")

    def validate_template(self, template: NotificationTemplate) -> Dict[str, Any]:

        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'required_variables': []
        }

        try:
            subject_vars = self._extract_variables(template.subject)
            body_vars = self._extract_variables(template.body)
            all_variables = list(set(subject_vars + body_vars))

            validation_result['required_variables'] = all_variables

            self._validate_django_syntax(template.subject)
            self._validate_django_syntax(template.body)

            missing_vars = set(all_variables) - set(template.variables)
            if missing_vars:
                validation_result['warnings'].append(
                    f"Variables found in template but not declared: {', '.join(missing_vars)}"
                )

            unused_vars = set(template.variables) - set(all_variables)
            if unused_vars:
                validation_result['warnings'].append(
                    f"Declared variables not used in template: {', '.join(unused_vars)}"
                )

        except Exception as e:
            validation_result['is_valid'] = False
            validation_result['errors'].append(str(e))

        return validation_result

    def get_template_preview(
        self,
        template: NotificationTemplate,
        sample_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:

        if sample_data is None:
            sample_data = self._generate_sample_data(template.variables)

        try:
            return self.render_template(template, sample_data)
        except Exception as e:
            return {
                'subject': f"[Error: {str(e)}]",
                'body': f"[Error: {str(e)}]"
            }

    def create_template(
        self,
        name: str,
        subject: str,
        body: str,
        template_type: str,
        variables: Optional[list] = None
    ) -> NotificationTemplate:

        if variables is None:
            variables = []

        template = NotificationTemplate(
            name=name,
            subject=subject,
            body=body,
            template_type=template_type,
            variables=variables
        )

        validation = self.validate_template(template)
        if not validation['is_valid']:
            raise ValueError(f"Ошибка валидации шаблона: {', '.join(validation['errors'])}")

        template.save()
        logger.info(f"Создан шаблон {name} для {template_type}")

        return template

    def _render_string(self, template_string: str, context_data: Dict[str, Any]) -> str:

        try:
            template = Template(template_string)
            context = Context(context_data)
            return template.render(context)

        except TemplateSyntaxError as e:
            raise ValueError(f"Ошибка синтаксиса шаблона: {str(e)}")
        except Exception as e:
            raise ValueError(f"Ошибка рендеринга шаблона: {str(e)}")

    def _extract_variables(self, template_string: str) -> list:

        variable_pattern = r'\{\{\s*(\w+)\s*\}\}'
        matches = re.findall(variable_pattern, template_string)
        return list(set(matches))

    def _validate_django_syntax(self, template_string: str):

        try:
            Template(template_string)
        except TemplateSyntaxError as e:
            raise ValueError(f"Неверный синтаксис Django шаблона: {str(e)}")

    def _generate_sample_data(self, variables: list) -> Dict[str, Any]:

        sample_data = {}

        for var in variables:
            if 'name' in var.lower():
                sample_data[var] = 'Иван Петров'
            elif 'email' in var.lower():
                sample_data[var] = 'user@example.com'
            elif 'phone' in var.lower():
                sample_data[var] = '+7 (999) 123-45-67'
            elif 'date' in var.lower():
                sample_data[var] = '2024-01-15'
            elif 'time' in var.lower():
                sample_data[var] = '14:30'
            elif 'code' in var.lower():
                sample_data[var] = '123456'
            elif 'url' in var.lower() or 'link' in var.lower():
                sample_data[var] = 'https://example.com'
            elif 'amount' in var.lower() or 'sum' in var.lower():
                sample_data[var] = '1000.00'
            else:
                sample_data[var] = f'[{var}]'

        return sample_data