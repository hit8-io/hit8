import { defineField, defineType, defineArrayMember } from 'sanity'
import { HomeIcon } from '@sanity/icons'

export default defineType({
  name: 'home',
  title: 'Home Page',
  type: 'document',
  icon: HomeIcon,
  fields: [
    defineField({
      name: 'hero',
      type: 'hero',
      title: 'Hero Section',
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: 'features',
      type: 'array',
      title: 'Features',
      of: [
        defineArrayMember({
          type: 'feature',
        }),
      ],
      validation: (rule) => rule.required().min(1),
    }),
  ],
})
