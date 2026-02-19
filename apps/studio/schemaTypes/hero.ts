import { defineField, defineType } from 'sanity'
import { SparklesIcon } from '@sanity/icons'

export default defineType({
  name: 'hero',
  title: 'Hero Section',
  type: 'object',
  icon: SparklesIcon,
  fields: [
    defineField({ name: 'badge', type: 'string', title: 'Badge Text' }),
    defineField({ name: 'headline', type: 'string', title: 'Main Headline' }),
    defineField({ name: 'subHeadline', type: 'string', title: 'Gradient Headline' }),
    defineField({ name: 'description', type: 'text', title: 'Description' }),
  ],
})
