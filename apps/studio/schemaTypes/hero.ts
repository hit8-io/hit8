import { defineField, defineType } from 'sanity'
import { SparklesIcon } from '@sanity/icons'

export default defineType({
  name: 'hero',
  title: 'Hero Section',
  type: 'object',
  icon: SparklesIcon,
  fields: [
    defineField({
      name: 'badge',
      type: 'string',
      title: 'Badge Text',
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: 'headline',
      type: 'string',
      title: 'Main Headline',
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: 'subHeadline',
      type: 'string',
      title: 'Gradient Headline',
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: 'description',
      type: 'text',
      title: 'Description',
      validation: (rule) => rule.required(),
    }),
  ],
})
